import click
from vcl_utils.logging import configure_logging

from app.config import Settings
from app.workspace import check_workspaces_activity


@click.group()
@click.option("--debug/--no-debug", default=False)
def supervisor_cli(debug):
    click.echo(f"Debug mode is {'on' if debug else 'off'}")


@supervisor_cli.command()
def run_workspaces_activity_cron():
    check_workspaces_activity()


@supervisor_cli.command()
def start():
    """
    TODO: this is an example for supervisor service daemon
    once we get to it – i.e. invoked as:
    python supervisor.py start
    """
    click.echo("Workspace supervisor service will be coming soon!")


if __name__ == "__main__":
    # configure logging
    configure_logging(app_name=Settings.APP_NAME)
    supervisor_cli()
