import time
import logging
from contextlib import closing
from typing import Optional, Any

import redis
from django.core.management import BaseCommand
from django.conf import settings
from django.db import connections

from vcl.rabbitmq import publisher

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check readiness by database, redis and rabbitmq connections"

    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        start = time.time()
        # test rabbitmq connection by sending a test message to rabbitmq.
        try:
            publisher.publish("test.message", "ping")
        except Exception:
            logger.exception("RabbitMQ connection failed.")
            exit(1)

        # test redis connection
        r = redis.Redis.from_url(settings.BROKER_URL)
        try:
            r.ping()
        except Exception:
            logger.exception("Redis connection failed.")
            exit(1)

        # test database connections
        try:
            for name in connections:
                with closing(connections[name].cursor()) as cursor:
                    cursor.execute("SELECT 1;")
                    row = cursor.fetchone()

                if row is None:
                    logger.error("Invalid response from database")
                    exit(1)
        except Exception:
            logger.exception("DB connection failed.")
            exit(1)

        logger.info("Readiness checks succeeded in %d seconds.", time.time() - start)

        exit(0)
