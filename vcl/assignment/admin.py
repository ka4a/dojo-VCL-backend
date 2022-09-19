from django.contrib import admin

from .models import (
    Assignment,
    AssignmentTag,
    Submission,
    WorkspaceConfiguration,
    WorkspaceAllocation,
    WorkspaceSession,
    WorkspaceUser,
)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )


@admin.register(AssignmentTag)
class AssignmentTagAdmin(admin.ModelAdmin):
    list_display = ["tag"]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "workspace_allocation_assignment",
        "workspace_allocation_user",
        "attempt_number",
    )

    @admin.display(description="Assignment")
    def workspace_allocation_assignment(self, obj):
        return obj.workspace_allocation.assignment.name

    @admin.display(description="learner")
    def workspace_allocation_user(self, obj):
        return obj.workspace_allocation.learner.id


@admin.register(WorkspaceConfiguration)
class WorkspaceConfigurationAdmin(admin.ModelAdmin):
    list_display = ("assignment", "docker_image")


@admin.register(WorkspaceAllocation)
class WorkspaceAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "assignment",
        "learner",
        "workspace_status",
        "workspace_url",
        "created_at",
    )


@admin.register(WorkspaceSession)
class WorkspaceSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "expires_at",
        "is_expired",
        "status",
        "created",
        "modified",
    )


@admin.register(WorkspaceUser)
class WorkspaceUserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "last_access",
        "roles",
    )
