import time
import logging
from urllib.parse import urljoin

from django.utils import timezone
from django.conf import settings
from kubernetes import config, client

from .resources import (
    Namespace,
    Service,
    Secret,
    Deployment,
    IngressRoute,
    ForwardAuthMiddleware,
    StripPrefixMiddleware,
)
from .utils import get_k8s_api_client

logger = logging.getLogger(__name__)

if settings.APP_ENV == "DEV":
    config.load_incluster_config()


class Workspace:
    """
    Workspace Class reprenting the instance of an allocated
    student workspace in Kubernetes
    """

    namespace: Namespace
    service: Service
    secret: Secret
    deployment: Deployment

    workspace_allocation = None

    _k8s_core_v1 = None
    _k8s_apps_v1 = None
    _ws_details = {
        "ws_url": None,
        "status": None,
        "last_checked_at": None,
    }

    def __init__(self, workspace_allocation) -> None:
        self.workspace_allocation = workspace_allocation

        # initialize k8s api clients
        api_client = get_k8s_api_client()
        self._k8s_core_v1 = client.CoreV1Api(api_client=api_client)
        self._k8s_apps_v1 = client.AppsV1Api(api_client=api_client)

        # initialize k8s resources
        params = {
            "workspace_allocation": self.workspace_allocation,
            "api_client": api_client,
        }

        self.namespace = Namespace(**params)
        self.secret = Secret(**params)
        self.deployment = Deployment(**params)
        self.service = Service(**params)
        self.strip_prefix_mw = StripPrefixMiddleware(**params)
        self.forward_auth_mw = ForwardAuthMiddleware(**params)
        self.ingress_route = IngressRoute(**params)

    @property
    def details(self):
        return self._ws_details

    @property
    def status(self):
        namespace_name = self.namespace.namespace
        pods = self._k8s_core_v1.list_namespaced_pod(namespace=namespace_name).items
        if pods:
            pod_status = pods[0].status
            if pod_status.container_statuses[0].ready:
                return pod_status.phase

    def get_ws_url(self):
        return urljoin(
            f"{settings.INGRESS_PROTOCOL}://{settings.INGRESS_HOST}",
            f"workspace/{self.workspace_allocation.workspace_url_slug}/",
        )

    def update_ws_details_from_cluster(self, wait_for_readiness=False):
        """
        Update workspace details from the cluster.

        Arguments:
          wait_for_readiness: Wait until the workspace is ready in 7 retries.
        """

        def wait_for_workload_to_be_ready():
            retries = 7
            non_ready_statuses = [None, "Pending"]
            ws_status = self.status
            workspace_name = self.namespace.namespace
            while ws_status in non_ready_statuses and retries > 0:
                retries -= 1
                retry_in = 0.3 * (7 - retries)
                logger.info(
                    "Attempt#%d: Waiting for '%s' to be ready.. Retrying in %d ms",
                    7 - retries,
                    workspace_name,
                    retry_in,
                )
                time.sleep(retry_in)
                ws_status = self.status

                if retries == 0 and ws_status in non_ready_statuses:
                    ws_status = "Failed"

            return ws_status

        ws_status = None
        if wait_for_readiness:
            ws_status = wait_for_workload_to_be_ready()

        self._ws_details["status"] = ws_status
        self._ws_details["ws_url"] = self.get_ws_url()
        self._ws_details["last_checked_at"] = timezone.now()
        return self._ws_details

    def launch(self, wait_for_readiness=False):

        self.namespace.create()
        self.secret.create()
        self.service.create()
        self.deployment.create()
        self.strip_prefix_mw.create(group="traefik.containo.us", version="v1alpha1", plural="middlewares")
        self.forward_auth_mw.create(group="traefik.containo.us", version="v1alpha1", plural="middlewares")
        self.ingress_route.create(group="traefik.containo.us", version="v1alpha1", plural="ingressroutes")

        self.update_ws_details_from_cluster(wait_for_readiness=wait_for_readiness)

    def delete(self, drop_namespace=False):
        """
        Delete workspace pod.

        Arguments:
            drop_namespace: if set, drops the whole namespace and waits
            until namespace deletion is done and if its not set then, this
            just scales the workspace deployment down to 0 replicas.
        """
        self.deployment.scale(replicas=0)
        if drop_namespace:
            self.namespace.delete(wait_until_deleted=True)
