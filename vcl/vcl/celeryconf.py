import logging
from logging import config as logging_conf
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging
from django.conf import settings
from vcl_utils.logging import get_logging_config

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vcl.settings")

app = Celery("vcl")
app.config_from_object("django.conf:settings")
app.autodiscover_tasks()


@setup_logging.connect
def config_loggers(*args, **kwargs):
    logger_conf = get_logging_config(app_name="celery", include_ws_session=False)
    logging_conf.dictConfig(logger_conf)


app.conf.beat_schedule = (
    {
        "cleanup_expired_sessions": {
            "task": "assignment.tasks.cleanup_expired_sessions",
            "schedule": crontab(
                minute=0,
                hour="*",
                day_of_week="*",
                day_of_month="*",
                month_of_year="*",
            ),
        },
        "cleanup_sessions_older_than_max_duration_allowed": {
            "task": "assignment.tasks.cleanup_sessions_older_than_max_duration_allowed",
            "schedule": crontab(
                minute="*/20",
                hour="*",
                day_of_week="*",
                day_of_month="*",
                month_of_year="*",
            ),
        },
    }
    if settings.ENABLE_CELERY_PERIODIC_TASKS
    else {}
)
