import json
import logging
import ssl
from typing import Tuple
import pika

logger = logging.getLogger(__name__)


def get_ssl_options():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_context.set_ciphers("ECDHE+AESGCM:!ECDSA")
    return pika.SSLOptions(context=ssl_context)


class PublisherConnectionManager:
    log_prefix = "[PUBLISHER]"
    EXCHANGE = "vcl"
    TYPE = "topic"

    def __init__(self, rabbitmq_credentials: Tuple[str], rabbitmq_url: Tuple[str], configure_ssl: bool = False):
        credentials = pika.PlainCredentials(*rabbitmq_credentials)
        self._params = pika.connection.ConnectionParameters(*rabbitmq_url, credentials)

        if configure_ssl:
            self._configure_ssl()
        self._conn = None
        self._channel = None

    def _configure_ssl(self):
        self._params.ssl_options = get_ssl_options()

    def _connect(self):
        if not self._conn or self._conn.is_closed:
            self._conn = pika.BlockingConnection(self._params)
            self._channel = self._conn.channel()
            self._channel.exchange_declare(exchange=self.EXCHANGE, exchange_type=self.TYPE)
            logger.info(f"{self.log_prefix} Connected")

    def _close(self):
        if self._conn and self._conn.is_open:
            logger.info(f"{self.log_prefix} Closing queue connection")
            self._conn.close()

    def _reconnect(self):
        logger.info(f"{self.log_prefix} Reconnecting to queue")
        self._close()
        self._connect()

    def _publish(self, routing_key, msg):
        self._connect()
        self._channel.basic_publish(
            exchange=self.EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(msg).encode(),
        )
        logger.info(f"{self.log_prefix} Message {msg} sent to {routing_key}")

    def publish(self, routing_key, msg):
        """Publish msg, reconnecting if necessary."""

        try:
            self._publish(routing_key, msg)
        except (
            pika.exceptions.ConnectionClosed,
            pika.exceptions.ChannelWrongStateError,
            pika.exceptions.StreamLostError,
        ):
            self._reconnect()
            self._publish(routing_key, msg)

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._close()
