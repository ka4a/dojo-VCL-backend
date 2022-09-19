import logging
import pytz
import json
from datetime import datetime
from pprint import pformat

from kubernetes import client, watch, config
from vcl_utils.publisher import PublisherConnectionManager
from vcl_utils.eks import EKSAPIClient

from app.config import Settings

logger = logging.getLogger(__name__)

if Settings.APP_ENV == "DEV":
    config.load_incluster_config()


def get_k8s_api_client():
    api_client = None
    if Settings.APP_ENV != "DEV":
        eks = EKSAPIClient(eks_cluster_name=Settings.WORKSPACES_CLUSTER_NAME)
        api_client = eks.api_client

    return client.CoreV1Api(api_client=api_client)


def start_watch():
    """
    Watch events from kubernetes cluster infinitely for
    workspace namespaces.

    Workspace Pod Lifecycle Events:
    -------------------------------
    1. Scheduled
    2. Pulled (workpace-init)
    3. Created (workpace-init)
    4. Started (workpace-init)
    5. Pulled (wa-x)
    6. Created (wa-x)
    7. Started (wa-x)
    8. Killling (wa-x)
    """
    logger.info("Starting watcher")
    k8s_api = get_k8s_api_client()
    configure_ssl = Settings.APP_ENV != "DEV"
    with PublisherConnectionManager(
        Settings.RABBITMQ_CREDENTIALS, Settings.RABBITMQ_URL, configure_ssl=configure_ssl
    ) as publisher:
        while True:
            watch_obj = watch.Watch()
            watch_launched_at = datetime.now(pytz.utc)
            selection_criteria = (
                "metadata.namespace!=default,"
                "metadata.namespace!=test,"
                "metadata.namespace!=kube-system,"
                "metadata.namespace!=kube-public,"
                "metadata.namespace!=kube-node-lease,"
                "metadata.namespace!=vcl-core,"
                "involvedObject.kind=Pod"
            )
            try:
                for event in watch_obj.stream(k8s_api.list_event_for_all_namespaces, field_selector=selection_criteria):
                    event_obj = event["object"]
                    event_timestamp = event_obj.event_time or event_obj.last_timestamp or event_obj.first_timestamp
                    if event_timestamp < watch_launched_at:
                        # Skip any events that are older than
                        # the watcher service launch.
                        logger.info(
                            f"SKIPPING AN OLD EVENT: "
                            f"TIME: {event_timestamp} | "
                            f"TYPE: {event_obj.type} | "
                            f"REASON: {event_obj.reason} | "
                            f"MESSAGE: {event_obj.message}"
                        )
                        continue

                    # Make sure we only inspect workspace events
                    if event_obj.metadata.namespace.startswith(Settings.WORKSPACES_NAMESPACE_PREFIX):
                        logger.info(
                            f"[{event['type']}] TIME: {event_timestamp} | "
                            f"TYPE: {event_obj.type} | "
                            f"REASON: {event_obj.reason} | "
                            f"MESSAGE: {event_obj.message}"
                        )

                        # 1. Get workspace pod details from cluster.
                        try:
                            workspace_pod = k8s_api.read_namespaced_pod(
                                name=event_obj.involved_object.name,
                                namespace=event_obj.involved_object.namespace,
                            )
                        except client.ApiException as exc:
                            exc_info = json.loads(exc.body)
                            if exc_info["reason"] == "NotFound":
                                logger.info(f"No such workspace: '{event_obj.involved_object.namespace}'")
                                continue
                            raise

                        # 2. Prepare workspace meta information for consumer events
                        workspace_container_name = workspace_pod.spec.containers[0].name
                        workspace_meta = {
                            "assignment_id": workspace_pod.metadata.labels["assignment"],
                            "student_id": workspace_pod.metadata.labels["student"],
                            "workspace_allocation_id": workspace_pod.metadata.labels["workspace_allocation"],
                        }

                        # 3. Send events, relevant to pod life cycle, to consumer.
                        event_type = event_obj.reason.upper()
                        if event_type == "SCHEDULED" and workspace_container_name in event_obj.message:
                            publisher.publish("k8s.workspace.scheduled", workspace_meta)
                        elif event_type == "CREATED" and workspace_container_name in event_obj.message:
                            publisher.publish("k8s.workspace.created", workspace_meta)
                        elif event_type == "STARTED" and workspace_container_name in event_obj.message:
                            publisher.publish("k8s.workspace.started", workspace_meta)
                        elif event_type in ["FAILED", "BACKOFF"]:
                            publisher.publish("k8s.workspace.failed", workspace_meta)
                        elif event_type == "KILLING" and workspace_container_name in event_obj.message:
                            publisher.publish("k8s.workspace.deleted", workspace_meta)
                        else:
                            # workspace is not ready yet, log container statuses
                            for container_status_field in [
                                "container_statuses",
                                "init_container_statuses",
                            ]:
                                container_statuses = getattr(workspace_pod.status, container_status_field)
                                if container_statuses and (container_status := container_statuses[0]):
                                    logger.info(
                                        f"container={container_status.name} "
                                        f"state={container_status.state} ready={container_status.ready}"
                                    )
                                else:
                                    logger.info(
                                        "Pod '%s' has not been scheduled into any node yet", workspace_pod.metadata.name
                                    )
            except client.ApiException as exc:
                if exc.status == 410:
                    # Reinitialize watcher on 410 – resourceVersion for the provided watch is too old
                    # ref: https://github.com/kubernetes/kubernetes/issues/72187
                    exc_info = json.loads(exc.body)
                    logger.info("Encountered 410 API response: %s", pformat(exc_info))
                    continue
                else:
                    raise
