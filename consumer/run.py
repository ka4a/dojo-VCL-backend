import click
import redis
from vcl_utils.logging import configure_logging

from app.config import Settings
from app.consumer import Consumer


@click.group()
@click.option("--debug/--no-debug", default=False)
def consumer_cli(debug):
    click.echo(f"Debug mode is {'on' if debug else 'off'}")


@consumer_cli.command()
def check_readiness():
    """
    Cli to check consumer's readiness.
    """
    # test rabbitmq connection
    consumer = Consumer()
    consumer.test_connection()

    # test redis connection
    r = redis.Redis.from_url(Settings.CELERY_BROKER_URL)
    try:
        r.ping()
        exit(0)
    except (redis.exceptions.ConnectionError, ConnectionRefusedError):
        exit(1)


@consumer_cli.command()
def start_consumer():
    consumer = Consumer()
    consumer.start()


if __name__ == "__main__":
    # configure logging
    configure_logging(app_name=Settings.APP_NAME)
    consumer_cli()
