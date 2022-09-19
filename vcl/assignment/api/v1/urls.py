from django.urls import path

from .views import WorkspaceLaunchStatusAPIView

urlpatterns = [
    path(
        "workspace/status/",
        WorkspaceLaunchStatusAPIView.as_view(),
        name="ws-launch-status",
    ),
]
