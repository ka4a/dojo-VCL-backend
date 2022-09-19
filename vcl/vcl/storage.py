import json
import boto3
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class EBSVolume:
    """
    Management of EBS Volumes for student workspaces
    """

    def __init__(
        self,
        workspace_allocation=None,
        aws_region=settings.DEFAULT_AWS_REGION,
        aws_availability_zone=settings.DEFAULT_AWS_AVAILABILITY_ZONE,
    ):

        self.workspace_allocation = workspace_allocation
        self.aws_region = aws_region
        self.aws_availability_zone = aws_availability_zone
        self.volume_id = None
        self.volume_size_gb = self.workspace_allocation.workspace_configuration.storage_size

        session = boto3.Session()
        self._ec2_client = session.client("ec2", region_name=aws_region)

        return self._get_or_create_volume()

    def _get_or_create_volume(self):
        if not self.workspace_allocation.volume:
            volume = self._create_volume()

            self.workspace_allocation.volume = {
                "id": volume["VolumeId"],
                "region": self.aws_region,
                "availability_zone": self.aws_availability_zone,
            }
            self.workspace_allocation.save(update_fields=["volume"])

            logger.info(f"Created volume {volume['VolumeId']} for workspace {self.workspace_allocation.id}")
        else:
            # TODO: Handle volume not found and other ClientError Exceptions
            volumes = self._ec2_client.describe_volumes(
                VolumeIds=[self.workspace_allocation.volume["id"]],
                Filters=[
                    {
                        "Name": "availability-zone",
                        "Values": [
                            self.workspace_allocation.volume["availability_zone"],
                        ],
                    },
                ],
            )

            if not volumes["Volumes"]:
                raise Exception("Workspace allocation volume not found.")
            volume = volumes["Volumes"][0]
            logger.info(f"Using existing volume {volume['VolumeId']} for workspace {self.workspace_allocation.id}")
        self.volume_id = volume["VolumeId"]
        self.volume_size_gb = volume["Size"]

    def _create_volume(self, volume_name=None):
        if volume_name is None:
            volume_name = f"vcl-wa-{self.workspace_allocation.id}"

        new_volume = self._ec2_client.create_volume(
            AvailabilityZone=self.aws_availability_zone,
            Size=self.volume_size_gb,
            VolumeType="gp3",
            TagSpecifications=[
                {
                    "ResourceType": "volume",
                    # TODO: Add proper tags for student, assignment and workspace alloc.
                    "Tags": [
                        {"Key": "Name", "Value": volume_name},
                        {
                            "Key": "WorkspaceAllocation",
                            "Value": str(self.workspace_allocation.id),
                        },
                        {
                            "Key": "Type",
                            "Value": "WorkspaceAssignmentStorage",
                        },
                        {
                            "Key": "Env",
                            "Value": settings.APP_ENV_SHORT,
                        },
                        {
                            "Key": "Cleanup",
                            "Value": json.dumps(settings.APP_ENV_SHORT == "test"),
                        },
                    ],
                }
            ],
        )

        return new_volume
