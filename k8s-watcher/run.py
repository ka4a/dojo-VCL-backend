import click
import logging

from vcl_utils.logging import configure_logging
from vcl_utils.publisher import PublisherConnectionManager

from app.watcher import start_watch, get_k8s_api_client
from app.config import Settings

logger = logging.getLogger(__name__)


@click.group()
@click.option("--debug/--no-debug", default=False)
def watcher_cli(debug):
    click.echo(f"Debug mode is {'on' if debug else 'off'}")


@watcher_cli.command()
def check_readiness():
    # test rabbitmq connection
    try:
        configure_ssl = Settings.APP_ENV != "DEV"
        with PublisherConnectionManager(
            Settings.RABBITMQ_CREDENTIALS, Settings.RABBITMQ_URL, configure_ssl=configure_ssl
        ) as publisher:
            publisher.publish("test.connection", {})
    except Exception:
        logger.exception("Connection to RabbitMQ failed")
        exit(1)

    # test k8s cluster access
    client = get_k8s_api_client()
    try:
        client.list_namespace()
    except Exception:
        exit(1)


@watcher_cli.command()
def start_watcher():
    start_watch()


if __name__ == "__main__":
    # configure logger
    configure_logging(app_name=Settings.APP_NAME)
    watcher_cli()
