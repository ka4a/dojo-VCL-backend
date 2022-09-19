import logging

from django.db import models
from rest_framework.permissions import BasePermission

from assignment.models import WorkspaceSession

logger = logging.getLogger(__name__)


class IsWorkspaceUser(BasePermission):
    message = "Permission denied"

    def has_permission(self, request, view):
        """
        Permission is denied in case of either of the following:
            1. Workspace user is not found in django session
            2. Workspace allocation is not found in django session
            3. Specified workspace allocation does not have an active session
            4. workspace session has expired
        """
        workspace_user_id = request.session.get("workspace_user_id")
        workspace_allocation_id = request.session.get("workspace_allocation_id")

        if not workspace_user_id or not workspace_allocation_id:
            # No need to make DB call if request's session
            # is anonymous.
            return False

        active_session = (
            WorkspaceSession.objects.select_related("workspace_allocation__learner")
            .filter(
                models.Q(workspace_allocation_id=workspace_allocation_id)
                & (
                    models.Q(workspace_allocation__learner_id=workspace_user_id)
                    | models.Q(instructor_id=workspace_user_id)
                )
            )
            .active()
        )
        if not active_session.exists():
            logger.info("No active session for wa-%d", workspace_allocation_id)
            return False

        return True
