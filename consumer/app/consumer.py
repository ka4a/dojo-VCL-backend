import json
import logging

import pika
from pika.exceptions import AuthenticationError, AMQPConnectionError
from celery import Celery
from vcl_utils.publisher import get_ssl_options

from app.config import Settings

logger = logging.getLogger(__name__)

# Celery tasks to be called on specific message
# Empty list shows that events are being triggered / captured but
# we did not decide any action yet on them.
ROUTING_KEY_MAPPING = {
    "k8s.workspace.scheduled": [],
    "k8s.workspace.created": [],
    "k8s.workspace.started": ["assignment.tasks.start_workspace_session"],
    "k8s.workspace.failed": ["assignment.tasks.log_workspace_launch_failure"],
    "workspace.status.alive": ["assignment.tasks.extend_workspace_session"],
    "workspace.status.idle": ["assignment.tasks.terminate_workspace_session"],
}


class Consumer:
    """
    A RabbitMQ Consumer.
    """

    connection = None

    def __init__(self):
        self.connection = self.connect_consumer()
        self.celery = Celery(__name__, broker=Settings.CELERY_BROKER_URL)

    def connect_consumer(self):
        connection_params = pika.ConnectionParameters(
            *Settings.RABBITMQ_URL, pika.PlainCredentials(*Settings.RABBITMQ_CREDENTIALS)
        )
        if Settings.APP_ENV != "DEV":
            connection_params.ssl_options = get_ssl_options()

        return pika.BlockingConnection(connection_params)

    def start(self):
        channel = self.connection.channel()
        channel.exchange_declare(exchange="vcl", exchange_type="topic")
        result = channel.queue_declare(Settings.QUEUE_NAME, durable=True)
        queue_name = result.method.queue

        channel.queue_bind(exchange="vcl", queue=queue_name, routing_key="workspace.#")
        channel.queue_bind(exchange="vcl", queue=queue_name, routing_key="k8s.#")

        channel.basic_consume(queue=queue_name, on_message_callback=self.message_handler, auto_ack=True)

        logger.info("Started Consuming...")
        channel.start_consuming()

    def message_handler(self, ch, method, properties, body):
        logger.info("CONSUMER: Handling message %r:%r" % (method.routing_key, body))

        if method.routing_key in ROUTING_KEY_MAPPING:
            tasks = ROUTING_KEY_MAPPING[method.routing_key]
            logger.info("Forking celery tasks: %r" % tasks)
            for task in tasks:
                self.celery.send_task(
                    task,
                    args=[],
                    kwargs=json.loads(body),
                    queue="celery",  # Default queue for now
                )
        else:
            logger.error("Unknown message %r:%r" % (method.routing_key, body))

    def test_connection(self):
        """
        Test rabbitmq connection.
        """
        try:
            if self.connection.is_open:
                logger.debug("CONSUMER: Connection is OK!")
                self.connection.close()
        except (AMQPConnectionError, AuthenticationError):
            logger.exception("CONSUMER: connection failed.")
            exit(1)
