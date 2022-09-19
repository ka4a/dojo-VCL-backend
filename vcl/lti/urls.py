from django.urls import path

from .views import (
    login,
    launch,
    get_jwks,
    configure,
    submit,
    score,
    AuthCheckAPIView,
)

urlpatterns = [
    path("login/", login, name="lti-login"),
    path("auth/check/<int:workspace_allocation_id>/", AuthCheckAPIView.as_view(), name="lti-workspace-auth"),
    path("launch/", launch, name="lti-launch"),
    path("jwks/", get_jwks, name="lti-jwks"),
    path("configure/<str:launch_id>/<str:difficulty>/", configure, name="lti-configure"),
    path(
        "api/submission/<str:launch_id>/<int:workspace_allocation_id>/",
        submit,
        name="lti-create-submission",
    ),
    path(
        "api/score/<str:launch_id>/<int:workspace_allocation_id>/",
        score,
        name="lti-score-submission",
    ),
]
