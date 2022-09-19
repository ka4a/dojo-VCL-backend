from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from assignment.models import WorkspaceAllocation, WorkspaceUser

from .permissions import IsWorkspaceUser
from .serializers import WorkspaceAllocationSerializer


class WorkspaceLaunchStatusAPIView(APIView):
    """
    API to report workspace launch status.
    """

    permission_classes = (IsWorkspaceUser,)

    def get(self, request):
        wa = get_object_or_404(WorkspaceAllocation, id=request.session["workspace_allocation_id"])
        workspace_user = WorkspaceUser.objects.get(id=request.session["workspace_user_id"])
        return Response(
            data={
                "wa": WorkspaceAllocationSerializer(wa).data,
                "has_instructor_access": workspace_user.is_instructor(),
            },
            status=status.HTTP_200_OK,
        )
