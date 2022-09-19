import pika
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from vcl_utils.publisher import get_ssl_options
from vcl.celeryconf import app

RMQ_QUEUE_NAME = "dcl-queue"


class Command(BaseCommand):
    """
    A management command which clears app cache, consumer queue and celery queue. This
    is meant to use in tests environment that is after the tests complete.

    The `handle` method is the entrypoint when this command is exected.

    An example usage is as follow:

        python manage.py purge_queues
    """

    help = "Purges the consumer queue, app cache and clery queue."

    def purge_rabbitmq_queue(self):
        """
        This clears RMQ messages. Retry 3 times
        before marking it as a failure as its common
        with RMQ that results in `StreamLostError` in
        the first attempt.
        """
        connection_params = pika.ConnectionParameters(
            *settings.RABBITMQ_URL, pika.PlainCredentials(*settings.RABBITMQ_CREDENTIALS)
        )
        if settings.APP_ENV != "DEV":
            connection_params.ssl_options = get_ssl_options()

        max_attempts = 3
        for _ in range(max_attempts):
            try:
                connection = pika.BlockingConnection(connection_params)
                channel = connection.channel()
                channel.queue_purge(queue=RMQ_QUEUE_NAME)
                self.stdout.write(f"RMQ queue '{RMQ_QUEUE_NAME}' has been purged.")
                break
            except pika.exceptions.ChannelClosedByBroker as exc:
                raise CommandError(f"RMQ: Purging failed: '{exc.reply_text}'")
            except pika.exceptions.StreamLostError:
                continue

    def purge_cache(self):
        """
        This clears the cache.
        """
        if hasattr(settings, "CACHES"):
            cache.clear()
            self.stdout.write("The cache has been cleared.")
        else:
            raise CommandError("You have no cache configured.")

    def purge_celery_queue(self):
        """
        This purges celery queue.
        """
        app.control.purge()
        self.stdout.write("Celery queue has been purged.")

    def handle(self, *args, **kwargs):
        if settings.APP_ENV not in ["DEV", "TESTING"]:
            raise CommandError("This can be used only for TESTING or DEV environments")

        # clear the app cache.
        self.purge_cache()
        # clear celery queue.
        self.purge_celery_queue()
        # clear rabbitmq messages queue.
        self.purge_rabbitmq_queue()
