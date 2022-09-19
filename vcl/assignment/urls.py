from django.urls import path

from .views import WorkspaceLaunchView


urlpatterns = [
    path(
        "launch/",
        WorkspaceLaunchView.as_view(),
        name="workspace-launch-page",
    ),
]
