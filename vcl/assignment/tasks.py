import logging
import json

from workspace import Workspace
from vcl import celery_app
from kubernetes import client

from assignment.models import WorkspaceAllocation, WorkspaceSession
from workspace.utils import get_k8s_api_client

logger = logging.getLogger(__name__)


@celery_app.task
def launch_workspace(workspace_allocation_id):
    """
    This task is used to launch the workspace.
    """
    wa = WorkspaceAllocation.objects.get(id=workspace_allocation_id)
    workspace = Workspace(wa)
    workspace.launch(wait_for_readiness=False)


@celery_app.task
def scale_down_workspace(session_id):
    session = WorkspaceSession.objects.get(id=session_id)
    workspace = Workspace(session.workspace_allocation)
    workspace.deployment.scale(replicas=0)
    session.terminate()
    return session.workspace_allocation.id


@celery_app.task
def delete_workspace_namespace(workspace_allocation_id):
    workspace_allocation = WorkspaceAllocation.objects.get(id=workspace_allocation_id)
    workspace = Workspace(workspace_allocation)
    workspace.namespace.delete()


@celery_app.task
def cleanup_expired_sessions():
    """
    This task cleans up workspace pods for expired workspace sessions.
    """
    for session in WorkspaceSession.objects.expired().with_launched_workspace():
        # chain the tasks: scale_down_workspace -> delete_workspace_namespace
        scale_down_workspace.apply_async(args=(session.id,), link=delete_workspace_namespace.s())


@celery_app.task
def cleanup_sessions_older_than_max_duration_allowed():
    """
    This task cleans up workspace pods for workspace sessions
    that have been running for max duration allowed.
    """
    # Cleanup sessions that have reached their max duration
    for session in WorkspaceSession.objects.reached_max_duration():
        logger.info(
            "Cleaning up workspace on max duration for session=%s workspace_allocation=%s",
            session.id,
            session.workspace_allocation.id,
        )
        session.expire()
        # chain the tasks: scale_down_workspace -> delete_workspace_namespace
        scale_down_workspace.apply_async(args=(session.id,), link=delete_workspace_namespace.s())


@celery_app.task
def start_workspace_session(**kwargs):
    wa = WorkspaceAllocation.get_or_none(id=kwargs.get("workspace_allocation_id"))
    if wa and (session := wa.get_active_session()):
        wa.update_from_cluster()
        logger.info("Starting workspace session: %s", kwargs)
        session.start()
    else:
        logger.info("Workspace session not found")


@celery_app.task
def log_workspace_launch_failure(**kwargs):
    logger.info("K8s workspace launch failed: %s", kwargs)


@celery_app.task
def extend_workspace_session(**kwargs):
    wa = WorkspaceAllocation.get_or_none(id=kwargs.get("workspace_allocation_id"))
    if wa and (session := wa.get_active_session()):
        logger.info("Extending Workspace session: %s", kwargs)
        session.extend()
    else:
        logger.info("Workspace session not found")


@celery_app.task
def terminate_workspace_session(**kwargs):
    wa = WorkspaceAllocation.get_or_none(id=kwargs.get("workspace_allocation_id"))
    if wa and (session := wa.get_active_session()):
        session.expire()
        logger.info("Terminating Workspace session: %s", session.id)
        scale_down_workspace.apply_async(args=(session.id,), link=delete_workspace_namespace.s())
    else:
        logger.info("Workspace session not found")


@celery_app.task
def terminate_workspace_namespace_if_exists(wa_id):
    """
    This cleans up namespace which is running
    a stale workspace. Its a no-op if namespace
    is not present.
    """
    namespace = f"wa-{wa_id}"
    core_v1 = client.CoreV1Api(api_client=get_k8s_api_client())
    try:
        core_v1.delete_namespace(name=namespace)
    except client.ApiException as exc:
        exc_info = json.loads(exc.body)
        if exc_info["reason"] == "NotFound":
            logger.info("No such workspace: '%s'", namespace)
        else:
            raise
