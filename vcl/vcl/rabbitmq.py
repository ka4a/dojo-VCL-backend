import logging

from django.conf import settings
from vcl_utils.publisher import PublisherConnectionManager

logger = logging.getLogger(__name__)


publisher = PublisherConnectionManager(
    settings.RABBITMQ_CREDENTIALS,
    settings.RABBITMQ_URL,
    configure_ssl=settings.APP_ENV != "DEV",
)
