from dataclasses import dataclass

from vcl_utils.env import Env


@dataclass
class Settings:
    CELERY_BROKER_URL = Env.str("CELERY_BROKER_URL")
    RABBITMQ_CREDENTIALS = Env.list("RABBITMQ_CREDENTIALS")
    RABBITMQ_URL = Env.list("RABBITMQ_URL")
    APP_ENV = Env.str("ENVIRONMENT", default="DEV")
    APP_NAME = "consumer"
    QUEUE_NAME = Env.str("QUEUE_NAME", default="dcl-queue")
