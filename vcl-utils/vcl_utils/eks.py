import tempfile
import base64
from datetime import datetime, timedelta

import boto3
import pytz
from kubernetes import config, client
from botocore import session
from awscli.customizations.eks.get_token import (
    TokenGenerator,
    STSClientFactory,
    TOKEN_EXPIRATION_MINS,
)

client_factory = STSClientFactory(session=session.get_session())


class EKSAPIClient:
    """
    Retrieve k8s api client given an eks cluster.

    Provides API client having access to workspaces cluster for a limited amount of time.
    This is supposed to be used in place of default kubernetes.client.ApiClient.
    """

    def __init__(self, eks_cluster_name: str) -> None:
        self.eks_cluster_name = eks_cluster_name
        self.eks_cluster_data = self._get_eks_cluster_data()
        self.api_client = self._k8s_api_client()

    def _get_eks_cluster_data(self):
        eks = boto3.client("eks")
        cluster_data = eks.describe_cluster(name=self.eks_cluster_name)["cluster"]
        return cluster_data

    def _write_cafile(self, data: str) -> tempfile.NamedTemporaryFile:
        cafile = tempfile.NamedTemporaryFile(delete=False)
        cadata_b64 = data
        cadata = base64.b64decode(cadata_b64)
        cafile.write(cadata)
        cafile.flush()
        return cafile.name

    def _get_token(self) -> str:
        sts_client = client_factory.get_sts_client()
        expiry = datetime.now(pytz.utc) + timedelta(minutes=TOKEN_EXPIRATION_MINS)
        return TokenGenerator(sts_client).get_token(self.eks_cluster_name), expiry

    def _k8s_api_client(self):
        """
        Returns k8s api client given eks awscli client.
        """

        def _refresh_eks_token(kconfig):
            """
            A hook to refresh EKS token when it expires.
            """
            if kconfig.expiry <= datetime.now(pytz.utc):
                token, expiry = self._get_token()
                kconfig.api_key = {"authorization": f"Bearer {token}"}
                kconfig.expiry = expiry

        # Build k8s configuration with auth token and a hook
        # to refresh that auth token once expired.
        token, expiry = self._get_token()
        kconfig = config.kube_config.Configuration(
            host=self.eks_cluster_data["endpoint"],
            api_key={"authorization": f"Bearer {token}"},
        )
        kconfig.ssl_ca_cert = self._write_cafile(data=self.eks_cluster_data["certificateAuthority"]["data"])
        kconfig.expiry = expiry
        kconfig.refresh_api_key_hook = _refresh_eks_token
        return client.ApiClient(configuration=kconfig)
