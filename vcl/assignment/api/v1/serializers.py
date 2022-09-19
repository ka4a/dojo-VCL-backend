from rest_framework import serializers

from assignment.models import WorkspaceAllocation


class WorkspaceAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceAllocation
        fields = (
            "id",
            "workspace_url",
            "workspace_status",
            "workspace_status_updated_at",
            "debug",
        )
