from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied

from assignment.api.v1.permissions import IsWorkspaceUser


class WorkspaceUserAccessMixin(AccessMixin):
    """
    Decline permission if session does not have workspace user
    and its allocation information.
    """

    def dispatch(self, request, *args, **kwargs):
        if not IsWorkspaceUser().has_permission(request, None):
            raise PermissionDenied("Permission denied")

        return super().dispatch(request, *args, **kwargs)
