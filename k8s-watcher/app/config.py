from dataclasses import dataclass

from vcl_utils.env import Env


@dataclass
class Settings:
    RABBITMQ_CREDENTIALS = Env.list("RABBITMQ_CREDENTIALS")
    RABBITMQ_URL = Env.list("RABBITMQ_URL")
    APP_ENV = Env.str("ENVIRONMENT", default="DEV")
    WORKSPACES_CLUSTER_NAME = Env.str("WORKSPACES_CLUSTER_NAME")
    WORKSPACES_NAMESPACE_PREFIX = Env.str("WORKSPACES_NAMESPACE_PREFIX", default="wa-")
    APP_NAME = "k8s-watcher"
