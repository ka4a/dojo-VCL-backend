import base64

from django.conf import settings
from vcl_utils.eks import EKSAPIClient

__all__ = ["base64_encode", "get_k8s_api_client"]


def base64_encode(secret: str):
    return base64.b64encode(secret.encode("utf-8")).decode("utf-8")


def get_k8s_api_client():
    api_client = None
    if settings.APP_ENV != "DEV":
        eks = EKSAPIClient(settings.WORKSPACES_CLUSTER_NAME)
        api_client = eks.api_client
    return api_client
