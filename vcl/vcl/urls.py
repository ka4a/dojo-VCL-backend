from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.permissions import AllowAny

schema_view = get_schema_view(
    openapi.Info(
        title="VCL API",
        default_version="v1",
        description="VCL API Schema",
    ),
    url=f"{settings.INGRESS_PROTOCOL}://{settings.INGRESS_HOST}",
    public=True,
    permission_classes=(AllowAny,),
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include(
            [
                path(
                    "vcl/",
                    include(("assignment.api.v1.urls", "vcl"), namespace="vcl-v1"),
                ),
            ]
        ),
    ),
    path("assignment/", include(("assignment.urls", "vcl"), namespace="assignment")),
    path("lti/", include(("lti.urls", "vcl"), namespace="lti")),
    path("swagger/", schema_view.with_ui("swagger"), name="schema-swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
    ]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
