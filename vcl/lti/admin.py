from pylti1p3.contrib.django.lti1p3_tool_config.models import LtiToolKey
from pylti1p3.contrib.django.lti1p3_tool_config.admin import LtiToolKeyAdmin

from django.contrib import admin


class CustomLtiToolKeyAdmin(LtiToolKeyAdmin):
    """Custom Admin for LTI Tool Key"""

    change_fieldsets = ((None, {"fields": ("name", "public_key", "public_jwk")}),)


admin.site.unregister(LtiToolKey)
admin.site.register(LtiToolKey, CustomLtiToolKeyAdmin)
