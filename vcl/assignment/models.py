import logging
import uuid
from decimal import Decimal
from urllib.parse import urljoin

from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator
from django.contrib.postgres.fields import ArrayField
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from common.utils import CommonActionsMixin
from workspace import Workspace

logger = logging.getLogger(__name__)


def default_expiry():
    # kept default expiry same as workspace extentsion period
    return timezone.now() + timezone.timedelta(hours=settings.WORKSPACES_SESSION_EXTENSION_PERIOD)


class AssignmentTag(models.Model):
    tag = models.CharField(primary_key=True, max_length=20)

    def __str__(self):
        return self.name


# TODO: Adding xblock unit ID might allow to autogenerate LTI settings
class Assignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=250)
    lti_configuration = models.OneToOneField("lti1p3_tool_config.LtiTool", on_delete=models.SET_NULL, null=True)
    max_attempts = models.IntegerField(default=1)
    max_score = models.IntegerField(default=100)
    code_repo = models.URLField()

    tags = models.ManyToManyField(AssignmentTag, related_name="assignments", blank=True)

    def __str__(self):
        return f"{self.name}"


class Submission(models.Model):
    class Status(models.TextChoices):
        GRADING = "Grading"
        PASSED = "Passed"
        REJECTED = "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    workspace_allocation = models.ForeignKey(
        "assignment.WorkspaceAllocation",
        related_name="submissions",
        on_delete=models.CASCADE,
    )
    line_item_id = models.URLField(max_length=255)
    resource_link_id = models.CharField(max_length=255)
    attempt_number = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.GRADING,
    )

    def __str__(self):
        return f"Submission ID: {self.id}, WorkspaceAllocation ID: {self.workspace_allocation}, Status: {self.status}"


class WorkspaceConfiguration(models.Model):
    assignment = models.OneToOneField(
        "assignment.Assignment",
        on_delete=models.SET_NULL,
        related_name="workspace_configuration",
        null=True,
        blank=True,
    )
    docker_image = models.CharField(max_length=250)
    number_gpus = models.PositiveIntegerField(default=0)
    number_cpus = models.DecimalField(
        default=1,
        max_digits=2,
        decimal_places=1,
        validators=[MinValueValidator(Decimal("1.0"))],
        help_text="Number of CPUs the workspace can request. Minimum is 1CPU (Required by VSCode). Default is 1.",
    )
    amount_ram = models.DecimalField(
        default=2,
        max_digits=3,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("2.0"))],
        help_text="Amount of RAM, in GiB. Minimum is 2GiB (required by VSCode). Default is 2Gib.",
    )
    storage_size = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text=(
            "Persistent storage size (GiB) used for assignment files. System dependencies use a separated storage."
        ),
    )

    def __str__(self):
        return (
            f"< {self.id} | "
            f"docker_image: {self.docker_image} | "
            f"cpus: {float(self.number_cpus)} | "
            f"gpus: {self.number_gpus} | "
            f"ram: {float(self.amount_ram)}GB | "
            f"storage: {self.storage_size}GB >"
        )


class WorkspaceStatus(models.TextChoices):
    """
    This is in compliance to:
    https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-phase
    """

    PENDING = "Pending"
    RUNNING = "Running"
    FAILED = "Failed"
    UNKNOWN = "Unknown"


class WorkspaceAllocation(models.Model, CommonActionsMixin):
    class Meta:
        unique_together = (("assignment", "learner"),)

    assignment = models.ForeignKey(
        "assignment.Assignment",
        on_delete=models.CASCADE,
        related_name="workspace_allocations",
    )
    learner = models.ForeignKey(
        "assignment.WorkspaceUser",
        on_delete=models.CASCADE,
        related_name="workspace_allocations",
    )
    volume = models.JSONField(
        null=True,
        blank=True,
    )
    workspace_url_slug = models.UUIDField(unique=True, default=uuid.uuid4)

    # workspace metadata fields
    workspace_status = models.CharField(max_length=255, choices=WorkspaceStatus.choices, null=True, blank=True)
    workspace_status_updated_at = models.DateTimeField(null=True, blank=True)

    debug = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def workspace_url(self):
        return urljoin(
            f"{settings.INGRESS_PROTOCOL}://{settings.INGRESS_HOST}",
            f"/workspace/{self.workspace_url_slug}/",
        )

    @property
    def workspace_configuration(self):
        if hasattr(self.assignment, "workspace_configuration"):
            return self.assignment.workspace_configuration

    def get_last_submission_for_resource(self, resource_link_id):
        submissions = self.submissions.filter(resource_link_id=resource_link_id).distinct().order_by("attempt_number")
        return submissions.last()

    def remaining_attempts_for_resource(self, resource_link_id):
        remaining_attempts = self.assignment.max_attempts
        if submission := self.get_last_submission_for_resource(resource_link_id):
            remaining_attempts -= submission.attempt_number
        return remaining_attempts

    def get_active_session(self):
        """
        Get active session.
        """
        sessions = self.sessions.active()
        logger.info("Got %d active session for wa-%d", sessions.count(), self.id)
        try:
            session = sessions.latest("created")
        except WorkspaceSession.DoesNotExist:
            session = None

        return session

    def launch_workspace_async(self, instructor=None):
        """
        Launch workspace asynchronously.
        """
        from .tasks import launch_workspace

        # 1) Initiate workspace session
        active_session = self.get_active_session()
        if not active_session:
            WorkspaceSession.create_from_workspace_allocation(workspace_allocation=self, instructor=instructor)

        # 2) Launch workspace.
        launch_workspace.apply_async(args=(self.id,))

    def update_workspace_status(self, workspace_status):
        self.workspace_status = workspace_status
        self.workspace_status_updated_at = timezone.now()
        self.save(update_fields=["workspace_status", "workspace_status_updated_at"])

    def update_from_cluster(self):
        workspace = Workspace(self)
        workspace.update_ws_details_from_cluster(wait_for_readiness=True)
        self.update_workspace_status(workspace_status=workspace.details["status"])

    def get_id(self):
        return f"{self.assignment.id}:{self.learner.id}"

    def __str__(self):
        return f"<{self.id} | workspace status: {self.workspace_status} | learner: {self.learner.id}>"


@receiver(pre_delete, sender=WorkspaceAllocation, dispatch_uid="terminate_workspace_for_allocation_signal")
def terminate_workspace_for_allocation(sender, instance, using, **kwargs):
    from assignment.tasks import terminate_workspace_namespace_if_exists

    terminate_workspace_namespace_if_exists.apply_async(args=(instance.id,))


class WorkspaceSessionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_terminated=False, expires_at__gt=timezone.now())

    def expired(self):
        return self.select_related("workspace_allocation", "workspace_allocation__learner").filter(
            is_terminated=False, expires_at__lte=timezone.now()
        )

    def reached_max_duration(self):
        max_duration_hours_allowed_in_past = timezone.now() - timezone.timedelta(
            hours=settings.WORKSPACES_MAX_SESSION_DURATION
        )
        return (
            self.select_related("workspace_allocation", "workspace_allocation__learner")
            .filter(is_terminated=False, started_at__isnull=False)
            .filter(started_at__lte=max_duration_hours_allowed_in_past)
        )

    def with_launched_workspace(self):
        return self.filter(workspace_allocation__workspace_status=WorkspaceStatus.RUNNING)


class WorkspaceSession(models.Model, CommonActionsMixin):
    """
    This model contains workspace sessions
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    workspace_allocation = models.ForeignKey(
        "assignment.WorkspaceAllocation",
        related_name="sessions",
        on_delete=models.CASCADE,
    )
    instructor = models.ForeignKey("assignment.WorkspaceUser", null=True, blank=True, on_delete=models.SET_NULL)

    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=default_expiry)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_terminated = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    objects = WorkspaceSessionQuerySet.as_manager()

    def __str__(self):
        return f"<{self.id} | terminated: {self.is_terminated} | expired: {self.is_expired}>"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def status(self):
        now = timezone.now()
        if self.ended_at and self.ended_at <= now:
            return "Ended"
        elif self.expires_at <= now:
            return "Expired"
        elif self.started_at and self.started_at <= now:
            return "Started"
        else:
            return "Initiated"

    @classmethod
    def create_from_workspace_allocation(cls, workspace_allocation, instructor=None):
        return cls.objects.create(workspace_allocation=workspace_allocation, instructor=instructor)

    def start(self):
        self.started_at = timezone.now()
        self.save(update_fields=["started_at"])

    def extend(self):
        self.expires_at = timezone.now() + timezone.timedelta(hours=settings.WORKSPACES_SESSION_EXTENSION_PERIOD)
        self.save(update_fields=["expires_at"])

    def expire(self):
        self.expires_at = timezone.now()
        self.save(update_fields=["expires_at"])

    def terminate(self):
        self.is_terminated = True
        self.ended_at = timezone.now()
        self.save(update_fields=["is_terminated", "ended_at"])
        self.workspace_allocation.update_workspace_status(workspace_status=None)


class WorkspaceUser(models.Model, CommonActionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    last_access = models.DateTimeField(null=True, blank=True)
    roles = ArrayField(models.CharField(max_length=256), default=list)

    def is_instructor(self):
        return "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Instructor" in self.roles

    def __str__(self):
        return f"<{self.id} - Instructor: {self.is_instructor()}>"
