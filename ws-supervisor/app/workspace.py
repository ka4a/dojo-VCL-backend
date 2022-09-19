import pytz
import logging
import time
import asyncio
from typing import List, Dict
from datetime import datetime
import aiohttp
from kubernetes import client, config
from vcl_utils.publisher import PublisherConnectionManager

from app.config import Settings
from app.utils import gather_with_concurrency

__all__ = ["check_workspaces_activity"]
logger = logging.getLogger(__name__)

config.load_incluster_config()


def get_ws_healthz_url(service: client.V1Service) -> str:
    ws_base_url = f"{service.metadata.name}.{service.metadata.namespace}:{service.spec.ports[0].port}"
    return f"http://{ws_base_url}/healthz/"


async def pull_statuses_for_workspaces(workspaces: List[Dict[str, str]]):
    """
    A python coroutine that pulls healthz information
    for each workspace concurrently.
    """

    async def pull_workspace_status_async(session, healthz_url):
        async with session.get(healthz_url) as response:
            response.raise_for_status()
            result = await response.json(content_type=None)
            return result

    concurrency = 50
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        tasks = []
        for workspace in workspaces:
            task = asyncio.create_task(pull_workspace_status_async(session, workspace["healthz_url"]))
            tasks.append(task)

        logger.info("[asyncio] Tasks have been loaded for %d workspaces", len(workspaces))
        results = await gather_with_concurrency(concurrency, *tasks)
        logger.info("[asyncio] Got results for %d workspaces", len(results))
        return results


def should_proceed_with_workspace(workspace_pod: client.V1Pod) -> bool:
    """
    This checks whether workspace pod has been launched for at least 3 minutes.
    We do not want to remove a workspace which is just launched and user has not
    accessed it. `healthz/` respond with following in such cases:
    {'status': 'expired', 'lastHeartbeat': 0}
    """
    is_pod_ready = workspace_pod.status.container_statuses and workspace_pod.status.container_statuses[0].ready
    if is_pod_ready:
        for condition in workspace_pod.status.conditions:
            if condition.type == "Ready":
                time_since_started = datetime.now().replace(tzinfo=pytz.utc) - condition.last_transition_time
                # make sure its ready for at least 3 minutes.
                if time_since_started.total_seconds() >= 3 * 60:
                    return True

    return False


def check_workspaces_activity():
    """
    Pull workspace healthz status and send workspace.status.idle / workspace.status.alive
    to RMQ consumer depending on whether workspace is active or not and 5 minutes have past since
    last heartbeat.
    """
    k8s_api = client.CoreV1Api()
    configure_ssl = Settings.APP_ENV != "DEV"
    with PublisherConnectionManager(
        Settings.RABBITMQ_CREDENTIALS, Settings.RABBITMQ_URL, configure_ssl=configure_ssl
    ) as publisher:
        workspaces_to_process = []
        for workspace_pod in k8s_api.list_pod_for_all_namespaces(label_selector="pod=workspace").items:
            if should_proceed_with_workspace(workspace_pod):
                # Gather workspace labels and construct healthz urls.
                ws_namespace = workspace_pod.metadata.namespace
                ws_service = k8s_api.read_namespaced_service(name=ws_namespace, namespace=ws_namespace)
                workspaces_to_process.append(
                    {
                        "name": ws_namespace,
                        "labels": workspace_pod.metadata.labels,
                        "healthz_url": get_ws_healthz_url(ws_service),
                    }
                )

        if workspaces_to_process:
            ws_statuses = asyncio.run(pull_statuses_for_workspaces(workspaces_to_process))
            for idx, workspace in enumerate(workspaces_to_process):
                logger.info(f"Checking activity for workspace '{workspace['name']}'")
                workspace_status = ws_statuses[idx]
                workspace_meta = {
                    "assignment_id": workspace["labels"]["assignment"],
                    "student_id": workspace["labels"]["student"],
                    "workspace_allocation_id": workspace["labels"]["workspace_allocation"],
                }
                if workspace_status["status"] == "alive":
                    publisher.publish("workspace.status.alive", workspace_meta)
                else:
                    ws_last_heart_beat = workspace_status["lastHeartbeat"] / 1000
                    ws_idle_time_in_minutes = (time.time() - ws_last_heart_beat) / 60
                    logger.info(f"Workspace '{workspace['name']}' was idle for {ws_idle_time_in_minutes} minutes.")
                    if ws_idle_time_in_minutes >= 5:
                        publisher.publish("workspace.status.idle", workspace_meta)
        else:
            logger.info("No workpaces to process.")
