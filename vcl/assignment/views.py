from typing import Any, Dict

from django.views.generic import TemplateView
from django.urls import reverse

from .mixins import WorkspaceUserAccessMixin


class WorkspaceLaunchView(WorkspaceUserAccessMixin, TemplateView):
    template_name = "launch.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["workspace_launch_status_url"] = reverse("vcl-v1:ws-launch-status")
        return context
