import logging

logger = logging.getLogger(__name__)


class CommonActionsMixin:
    @classmethod
    def get_or_none(cls, **filter_criteria):
        return cls.objects.filter(**filter_criteria).first()
