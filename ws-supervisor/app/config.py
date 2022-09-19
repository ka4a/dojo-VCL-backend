from dataclasses import dataclass

from vcl_utils.env import Env


@dataclass
class Settings:
    RABBITMQ_CREDENTIALS = Env.list("RABBITMQ_CREDENTIALS")
    RABBITMQ_URL = Env.list("RABBITMQ_URL")
    APP_ENV = Env.str("ENVIRONMENT", default="DEV")
    APP_NAME = "WS-Supervisor"
