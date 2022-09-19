import logging

from pylti1p3.contrib.django import (
    DjangoMessageLaunch,
    DjangoCacheDataStorage,
    DjangoDbToolConf,
)

logger = logging.getLogger(__name__)


def get_launch_data_storage():
    return DjangoCacheDataStorage()


def get_tool_conf():
    tool_conf = DjangoDbToolConf()
    return tool_conf


class ExtendedDjangoMessageLaunch(DjangoMessageLaunch):
    def validate_nonce(self):
        """
        Probably it is bug on "https://lti-ri.imsglobal.org":
        site passes invalid "nonce" value during deep links launch.
        Because of this in case of iss == http://imsglobal.org just skip nonce validation.

        """
        iss = self.get_iss()
        deep_link_launch = self.is_deep_link_launch()
        if iss == "http://imsglobal.org" and deep_link_launch:
            return self
        return super(ExtendedDjangoMessageLaunch, self).validate_nonce()
