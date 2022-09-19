import abc
import json
import logging
import time
from urllib.parse import urljoin
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from kubernetes import config, client

from vcl.storage import EBSVolume

from .utils import base64_encode

logger = logging.getLogger(__name__)

if settings.APP_ENV == "DEV":
    config.load_incluster_config()


class WorkspaceResource(abc.ABC):
    workspace_allocation = None
    namespace = None
    namespaced = True
    _manifest = None

    _k8s_core_v1 = None
    _k8s_apps_v1 = None
    _k8s_custom_api = None

    def __init__(self, workspace_allocation, namespace=None, api_client=None):
        self.workspace_allocation = workspace_allocation

        if namespace is None:
            self.namespace = f"wa-{self.workspace_allocation.id}"

        self._initialize_api_clients(api_client=api_client)

    def _initialize_api_clients(self, api_client):
        self._k8s_core_v1 = client.CoreV1Api(api_client=api_client)
        self._k8s_apps_v1 = client.AppsV1Api(api_client=api_client)
        self._k8s_custom_api = client.CustomObjectsApi(api_client=api_client)

    @property
    def _manifest():
        raise NotImplementedError("Define the manifest getter")

    @property
    def _api_handler():
        raise NotImplementedError("Define an API handler")

    def _skip_if_already_exists(self, *args, **kwargs):
        """
        Wraps actions into to suppress exceptions if resource already exists in cluster.

        Returns:
          resource or status if resource exists.
        """

        def __check_for_reraise(exc: client.ApiException):
            info = json.loads(exc.body)
            if (reason := info.get("reason").lower()) == "alreadyexists":
                return reason
            else:
                raise exc

        try:
            return self._api_handler(*args, **kwargs)
        except client.ApiException as exc:
            return __check_for_reraise(exc)

    def create(self, **kwargs):
        # create resource
        logger.debug(f"Creating resource {type(self).__name__} with manifest {self._manifest}")
        if self.namespaced:
            kwargs["namespace"] = self.namespace

        result = self._skip_if_already_exists(body=self._manifest, **kwargs)
        return result


class Namespace(WorkspaceResource):
    namespaced = False

    @property
    def _manifest(self):

        return {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "label": self.namespace,
                "name": self.namespace,
            },
        }

    @property
    def _api_handler(self):
        return self._k8s_core_v1.create_namespace

    def delete(self, wait_until_deleted=True):
        """
        Delete this resource with all the resources inside
        the namespace.
        """
        try:
            self._k8s_core_v1.delete_namespace(name=self.namespace)
        except client.ApiException as exc:
            exc_info = json.loads(exc.body)
            if exc_info["reason"] == "NotFound":
                logger.info("No such workspace: '%s'", self.namespace)
                return

        if wait_until_deleted:
            while True:
                try:
                    self._k8s_core_v1.read_namespace(name=self.namespace)
                    logger.info("Waiting for namespace %s to terminate..", self.namespace)
                    time.sleep(1)
                except client.ApiException:
                    break

            logger.info("Deleted '%s' successfully.", self.namespace)
        else:
            logger.info("Removal has been started for '%s'.", self.namespace)


class Secret(WorkspaceResource):
    password = settings.WORKSPACE_DEFAULT_VSCODE_PASSWORD

    @property
    def _manifest(self):

        return {
            "apiVersion": "v1",
            "type": "Opaque",
            "kind": "Secret",
            "data": {"PASSWORD": base64_encode(self.password)},
            "metadata": {"name": self.namespace},
        }

    @property
    def _api_handler(self):
        return self._k8s_core_v1.create_namespaced_secret


class Deployment(WorkspaceResource):
    """
    A Class used to represent learner workspaces

    Notes on resources
    ------------------
    * Pods scheduling is done based on resource requests, not limits.
    * Limits larger the requests will allow for bursts of resources, using unallocated node resources.
    * We use memory limit because overusage of memory could crash nodes, which is not the case for CPUs.
    * Since initContainers don't run together with normal containers, scheduling of pods is based on
      effective resource requests, which is the highest between the sum of requests for all normal
      containers and the sum of requests for all initContainers. In our case we allow the same amount
      of resources for init containers and normal containers for clarity purpose.
    """

    ebs_volume = None
    WS_PUID = 1000
    WS_PGID = 1000
    WS_FS_GID = 1000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if settings.APP_ENV != "DEV":
            self.ebs_volume = EBSVolume(workspace_allocation=kwargs["workspace_allocation"])

    @property
    def _manifest(self):
        ws_conf = self.workspace_allocation.workspace_configuration
        image_name = ws_conf.docker_image

        num_gpus = ws_conf.number_gpus
        cpu_request = ws_conf.number_cpus * Decimal(settings.CPU_REQUEST_MULTIPLIER)
        cpu_limit = ws_conf.number_cpus * Decimal(settings.CPU_BURST_MULTIPLIER)
        memory_request = ws_conf.amount_ram * Decimal(settings.MEMORY_REQUEST_MULTIPLIER)
        memory_limit = memory_request * Decimal(settings.MEMORY_BURST_MULTIPLIER)

        wa_id = str(self.workspace_allocation.id)
        learner_id = str(self.workspace_allocation.learner.id)
        assignment_id = str(self.workspace_allocation.assignment.id.hex)

        code_repo = str(self.workspace_allocation.assignment.code_repo)

        manifest = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": self.namespace,
                "labels": {
                    "app": self.namespace,
                    "student": learner_id,
                    "assignment": assignment_id,
                    "workspace_allocation": wa_id,
                },
            },
            "spec": {
                "selector": {
                    "matchLabels": {
                        "workspace_allocation": wa_id,
                    }
                },
                "strategy": {"type": "Recreate"},
                "template": {
                    "metadata": {
                        "labels": {
                            "pod": "workspace",
                            "app": self.namespace,
                            "student": learner_id,
                            "assignment": assignment_id,
                            "workspace_allocation": wa_id,
                        }
                    },
                    "spec": {
                        "automountServiceAccountToken": False,
                        "containers": [
                            {
                                "image": image_name,
                                "imagePullPolicy": "IfNotPresent",
                                "name": self.namespace,
                                "envFrom": [{"secretRef": {"name": self.namespace}}],
                                "command": [
                                    "bash",
                                    "/usr/bin/entrypoint.sh",
                                    "--auth",
                                    "none",
                                    "--disable-update-check",
                                    "--disable-telemetry",
                                    "--bind-addr",
                                    "0.0.0.0:8080",
                                    settings.USER_ASSIGNMENT_FOLDER,
                                ],
                                "readinessProbe": {
                                    "httpGet": {"path": "/healthz", "port": 8080},
                                    "periodSeconds": 10,
                                    "timeoutSeconds": 5,
                                    "failureThreshold": 2,
                                },
                                "env": [
                                    {"name": "PUID", "value": str(self.WS_PUID)},
                                    {"name": "PGID", "value": str(self.WS_PGID)},
                                ],
                                "resources": {
                                    "requests": {"cpu": str(cpu_request), "memory": f"{memory_request}Gi"},
                                    "limits": {"cpu": str(cpu_limit), "memory": f"{memory_limit}Gi"},
                                },
                                "ports": [
                                    {
                                        "containerPort": 8080,
                                        "name": self.namespace,
                                    }
                                ],
                                "volumeMounts": [
                                    {
                                        "name": f"user-volume-{self.namespace}",
                                        "mountPath": "/home/coder",
                                        "subPath": "user-home",
                                    },
                                ],
                                "securityContext": {"runAsUser": self.WS_PUID, "runAsGroup": self.WS_PGID},
                            },
                        ],
                        "initContainers": [
                            {
                                "name": "init-workspace",
                                "env": [
                                    {"name": "WS_PUID", "value": str(self.WS_PUID)},
                                    {"name": "WS_PGID", "value": str(self.WS_PGID)},
                                    {"name": "GH_ACCESS_TOKEN", "value": settings.GITHUB_ACCESS_TOKEN},
                                ],
                                "image": f"{settings.DOCKER_REGISTRY}vcl_init_container:{settings.INIT_CONTAINER_TAG}",
                                "imagePullPolicy": "Never" if settings.APP_ENV == "DEV" else "Always",
                                "resources": {
                                    "requests": {"cpu": str(cpu_request), "memory": f"{memory_request}Gi"},
                                    "limits": {"cpu": str(cpu_limit), "memory": f"{memory_limit}Gi"},
                                },
                                "command": [
                                    "python",
                                    "init-container.py",
                                    "--repo",
                                    code_repo,
                                    "--debug" if self.workspace_allocation.debug else "--no-debug",
                                ],
                                "volumeMounts": [
                                    {
                                        "name": f"user-volume-{self.namespace}",
                                        "mountPath": "/home/coder",
                                        "subPath": "user-home",
                                    }
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": f"user-volume-{self.namespace}"},
                        ],
                    },
                },
            },
        }

        if settings.APP_ENV != "DEV":
            # Target CPU node groups by default
            manifest["spec"]["template"]["spec"]["nodeSelector"] = {
                "eks.amazonaws.com/nodegroup": settings.CPU_NODE_GROUP_NAME
            }
            if num_gpus > 0:
                # Target GPU node groups
                manifest["spec"]["template"]["spec"]["nodeSelector"] = {
                    "eks.amazonaws.com/nodegroup": settings.GPU_NODE_GROUP_NAME
                }
                # Add GPU resource request
                manifest["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"] = {
                    "nvidia.com/gpu": num_gpus
                }

        if self.ebs_volume:
            manifest["spec"]["template"]["spec"]["volumes"][0]["awsElasticBlockStore"] = {
                "fsType": "ext4",
                "type": "gp3",
                "volumeID": self.ebs_volume.volume_id,
            }

        return manifest

    @property
    def _api_handler(self):
        return self._k8s_apps_v1.create_namespaced_deployment

    def scale(self, replicas):
        """
        Scale the Workspace deployment to the specified number of replicas.
        """
        try:
            self._k8s_apps_v1.patch_namespaced_deployment_scale(
                name=self.namespace, namespace=self.namespace, body={"spec": {"replicas": replicas}}
            )
        except client.ApiException as exc:
            exc_info = json.loads(exc.body)
            if exc_info["reason"] == "NotFound":
                logger.info("No such workspace: '%s'", self.namespace)


class Service(WorkspaceResource):
    @property
    def _manifest(self):

        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": self.namespace},
            "spec": {
                "type": "ClusterIP",
                "ports": [{"name": "http", "protocol": "TCP", "port": 8080, "targetPort": 8080}],
                "selector": {"app": self.namespace},
            },
        }

    @property
    def _api_handler(self):
        return self._k8s_core_v1.create_namespaced_service


class IngressRoute(WorkspaceResource):
    @property
    def _manifest(self):
        # Workspace static asset requests are not forwarded to web service for authorization.
        ws_static_routes = [
            {
                "match": f"PathPrefix(`/workspace/{self.workspace_allocation.workspace_url_slug}/static`)",
                "kind": "Rule",
                "services": [{"name": self.namespace, "port": "http"}],
                "middlewares": [{"name": f"strip-prefix-{self.namespace}"}],
            },
            {
                "match": f"PathPrefix(`/workspace/{self.workspace_allocation.workspace_url_slug}/_static`)",
                "kind": "Rule",
                "services": [{"name": self.namespace, "port": "http"}],
                "middlewares": [{"name": f"strip-prefix-{self.namespace}"}],
            },
        ]
        return {
            "apiVersion": "traefik.containo.us/v1alpha1",
            "kind": "IngressRoute",
            "metadata": {"name": self.namespace},
            "spec": {
                "entryPoints": ["web"],
                "routes": [
                    *ws_static_routes,
                    # Found the following workspace requests resulting in 404 with the following path prefix, adding
                    # those here so they don't mislead to web service anymore.
                    {
                        "match": ("PathPrefix(`/vs/workbench`)"),
                        "kind": "Rule",
                        "services": [{"name": self.namespace, "port": "http"}],
                        "middlewares": [
                            {"name": f"forward-auth-{self.namespace}"},
                        ],
                    },
                    # Everything else with /workspace/uuid prefix will be forwarded to web for auth.
                    {
                        "match": (f"PathPrefix(`/workspace/{self.workspace_allocation.workspace_url_slug}`)"),
                        "kind": "Rule",
                        "services": [{"name": self.namespace, "port": "http"}],
                        "middlewares": [
                            {"name": f"strip-prefix-{self.namespace}"},
                            {"name": f"forward-auth-{self.namespace}"},
                        ],
                    },
                ],
            },
        }

    @property
    def _api_handler(self):
        return self._k8s_custom_api.create_namespaced_custom_object


class ForwardAuthMiddleware(WorkspaceResource):
    @property
    def _manifest(self):
        return {
            "apiVersion": "traefik.containo.us/v1alpha1",
            "kind": "Middleware",
            "metadata": {"name": f"forward-auth-{self.namespace}"},
            "spec": {
                "forwardAuth": {
                    "address": urljoin(
                        settings.WORKSPACE_AUTH_BASE_URL,
                        reverse("lti:lti-workspace-auth", args=(self.workspace_allocation.id,)),
                    )
                }
            },
        }

    @property
    def _api_handler(self):
        return self._k8s_custom_api.create_namespaced_custom_object


class StripPrefixMiddleware(WorkspaceResource):
    @property
    def _manifest(self):
        return {
            "apiVersion": "traefik.containo.us/v1alpha1",
            "kind": "Middleware",
            "metadata": {
                "name": f"strip-prefix-{self.namespace}",
            },
            "spec": {"stripPrefix": {"prefixes": [f"/workspace/{self.workspace_allocation.workspace_url_slug}"]}},
        }

    @property
    def _api_handler(self):
        return self._k8s_custom_api.create_namespaced_custom_object
