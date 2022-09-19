from logging import config as logging_conf, Filter, LogRecord

from . import thread_local


def get_logging_config(app_name, include_ws_session=False):
    """
    Generate logging configuration for an application.
    """
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "app_formatter": {"format": f"[ {app_name} | %(levelname)s | %(asctime)s ] %(message)s"},
        },
        "handlers": {
            "stream_handler": {
                "class": "logging.StreamHandler",
                "formatter": "app_formatter",
            },
        },
        "root": {"level": "INFO", "handlers": ["stream_handler"], "propagate": False},
    }
    if include_ws_session:
        config["formatters"]["app_formatter"][
            "format"
        ] = f"[ {app_name} | %(levelname)s | %(asctime)s | %(workspace_session_id)s ] %(message)s"
        config["filters"] = {
            "ws_session_filter": {
                "()": "vcl_utils.logging.WorkspaceSessionLoggingFilter",
                "attr_name": "workspace_session_id",
            },
        }
        config["handlers"]["stream_handler"]["filters"] = [
            "ws_session_filter",
        ]

    return config


def configure_logging(app_name, include_ws_session=False):
    """
    Configure logging given and an app name.
    """
    logging_conf.dictConfig(config=get_logging_config(app_name, include_ws_session))


class WorkspaceSessionLoggingFilter(Filter):
    """
    Filter to set workspace session into LogRecord so could be
    utilized in the formatter.
    """

    def __init__(self, attr_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attr_name = attr_name

    def filter(self, record: LogRecord) -> bool:
        setattr(record, self.attr_name, getattr(thread_local, self.attr_name, None) or "-")
        return True


class CaptureWorkspaceSessionMiddleware:
    """
    A simple middleware that captures workspace session from the request in order for logger to read from
    thread local data.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if workspace_session_id := request.session.get("workspace_session_id"):
            thread_local.workspace_session_id = workspace_session_id

        return self.get_response(request)
