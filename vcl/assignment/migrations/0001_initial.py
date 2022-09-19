# Generated by Django 3.2.11 on 2022-04-08 11:19

import assignment.models
import common.utils
from decimal import Decimal
import django.contrib.postgres.fields
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("lti1p3_tool_config", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Assignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=250)),
                ("max_attempts", models.IntegerField(default=1)),
                ("max_score", models.IntegerField(default=100)),
                ("code_repo", models.URLField()),
                (
                    "lti_configuration",
                    models.OneToOneField(
                        null=True, on_delete=django.db.models.deletion.SET_NULL, to="lti1p3_tool_config.ltitool"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AssignmentTag",
            fields=[
                ("tag", models.CharField(max_length=20, primary_key=True, serialize=False)),
            ],
        ),
        migrations.CreateModel(
            name="WorkspaceAllocation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("volume", models.JSONField(blank=True, null=True)),
                ("workspace_url_slug", models.UUIDField(default=uuid.uuid4, unique=True)),
                (
                    "workspace_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("Pending", "Pending"),
                            ("Running", "Running"),
                            ("Failed", "Failed"),
                            ("Unknown", "Unknown"),
                        ],
                        max_length=255,
                        null=True,
                    ),
                ),
                ("workspace_status_updated_at", models.DateTimeField(blank=True, null=True)),
                ("debug", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_allocations",
                        to="assignment.assignment",
                    ),
                ),
            ],
            bases=(models.Model, common.utils.CommonActionsMixin),
        ),
        migrations.CreateModel(
            name="WorkspaceUser",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("last_access", models.DateTimeField(blank=True, null=True)),
                (
                    "roles",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256), default=list, size=None
                    ),
                ),
            ],
            bases=(models.Model, common.utils.CommonActionsMixin),
        ),
        migrations.CreateModel(
            name="WorkspaceSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(default=assignment.models.default_expiry)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("is_terminated", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "instructor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="assignment.workspaceuser",
                    ),
                ),
                (
                    "workspace_allocation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to="assignment.workspaceallocation",
                    ),
                ),
            ],
            bases=(models.Model, common.utils.CommonActionsMixin),
        ),
        migrations.CreateModel(
            name="WorkspaceConfiguration",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("docker_image", models.CharField(max_length=250)),
                ("number_gpus", models.PositiveIntegerField(default=0)),
                (
                    "number_cpus",
                    models.DecimalField(
                        decimal_places=1,
                        default=1,
                        help_text="Number of CPUs the workspace can request. Minimum is 1CPU (Required by VSCode). Default is 1.",
                        max_digits=2,
                        validators=[django.core.validators.MinValueValidator(Decimal("1.0"))],
                    ),
                ),
                (
                    "amount_ram",
                    models.DecimalField(
                        decimal_places=2,
                        default=2,
                        help_text="Amount of RAM, in GiB. Minimum is 2GiB (required by VSCode). Default is 2Gib.",
                        max_digits=3,
                        validators=[django.core.validators.MinValueValidator(Decimal("2.0"))],
                    ),
                ),
                (
                    "storage_size",
                    models.PositiveIntegerField(
                        default=2,
                        help_text="Persistent storage size (GiB) used for assignment files. System dependencies use a separated storage.",
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "assignment",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workspace_configuration",
                        to="assignment.assignment",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="workspaceallocation",
            name="learner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspace_allocations",
                to="assignment.workspaceuser",
            ),
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("line_item_id", models.URLField(max_length=255)),
                ("resource_link_id", models.CharField(max_length=255)),
                (
                    "attempt_number",
                    models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)]),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("Grading", "Grading"), ("Passed", "Passed"), ("Rejected", "Rejected")],
                        default="Grading",
                        max_length=10,
                    ),
                ),
                (
                    "workspace_allocation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="assignment.workspaceallocation",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="assignment",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="assignments", to="assignment.AssignmentTag"),
        ),
        migrations.AlterUniqueTogether(
            name="workspaceallocation",
            unique_together={("assignment", "learner")},
        ),
    ]