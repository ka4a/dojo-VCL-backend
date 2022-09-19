"""
Django settings for vcl project.
Generated by 'django-admin startproject' using Django 3.2.11.
For more information on this file, see
https://docs.djangoproject.com/en/3.2.11/topics/settings/
For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2.11/ref/settings/
"""
import os
from pathlib import Path

import environ

from vcl_utils.logging import get_logging_config

env = environ.Env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


ENVIRONMENTS = {
    "DEV": "dev",
    "TESTING": "test",
    "STAGING": "stg",
    "PRODUCTION": "prod",
}

APP_ENV = os.getenv("ENVIRONMENT", default="DEV")

assert APP_ENV in ENVIRONMENTS, "APP_ENV is not properly configured."

APP_ENV_SHORT = ENVIRONMENTS[APP_ENV]

DEBUG = os.getenv("DEBUG", default=APP_ENV == "DEV")

# AWS settings
DEFAULT_AWS_REGION = os.getenv("DEFAULT_AWS_REGION", default="ap-northeast-1")
DEFAULT_AWS_AVAILABILITY_ZONE = os.getenv("DEFAULT_AWS_AVAILABILITY_ZONE", default="ap-northeast-1a")
CPU_NODE_GROUP_NAME = env.str("CPU_NODE_GROUP_NAME", default="cpu-workspaces")
GPU_NODE_GROUP_NAME = env.str("GPU_NODE_GROUP_NAME", default="gpu-workspaces")

# Student workspace settings
WORKSPACE_DEFAULT_VSCODE_PASSWORD = env.str("WORKSPACE_DEFAULT_VSCODE_PASSWORD", default="")
WORKSPACE_AUTH_BASE_URL = env("WORKSPACE_AUTH_BASE_URL", default="http://auth.example.local/")
DOCKER_REGISTRY = env.str("DOCKER_REGISTRY")
INIT_CONTAINER_TAG = env.str("INIT_CONTAINER_TAG", default="latest")
WORKSPACES_CLUSTER_NAME = env.str("WORKSPACES_CLUSTER_NAME", default=None)
WORKSPACES_CLUSTER_TRAEFIK_NAMESPACE = env.str("WORKSPACES_CLUSTER_TRAEFIK_NAMESPACE", default=None)
WORKSPACES_CLUSTER_TRAEFIK_LABEL_VALUE = env.str("WORKSPACES_CLUSTER_TRAEFIK_LABEL_VALUE", default=None)
WORKSPACES_SESSION_EXTENSION_PERIOD = env.int("WORKSPACES_SESSION_EXTENSION_PERIOD", default=1)
WORKSPACES_MAX_SESSION_DURATION = env.int("WORKSPACES_MAX_SESSION_DURATION", default=6)
GITHUB_ACCESS_TOKEN = env.str("GITHUB_ACCESS_TOKEN", default=None)
USER_ASSIGNMENT_FOLDER = env.str("USER_ASSIGNMENT_FOLDER", default="/home/coder/assignment")
CODER_CONFIG_FOLDER = env.str("CODER_CONFIG_FOLDER", default="/home/coder/.config")

# Student workspace configuration
# We know workspaces will not run at their max and nodes will have resources
# to spare, so request less then minimum requirement but we allow bursts.
# We are more conservative with memory since OOM nodes might reboot.
CPU_REQUEST_MULTIPLIER = env.float("CPU_REQUEST_MULTIPLIER", default=0.75)
CPU_BURST_MULTIPLIER = env.float("CPU_BURST_MULTIPLIER", default=2)
MEMORY_REQUEST_MULTIPLIER = env.float("MEMORY_REQUEST_MULTIPLIER", default=0.9)
MEMORY_BURST_MULTIPLIER = env.float("MEMORY_BURST_MULTIPLIER", default=1.2)

# Ingress settings
INGRESS_PROTOCOL = env("INGRESS_PROTOCOL", default="http")
INGRESS_HOST = env("INGRESS_HOST", default="localhost")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2.11/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    "django_extensions",
    "debug_toolbar",
    "drf_yasg",
    "rest_framework",
    "pylti1p3.contrib.django.lti1p3_tool_config",
    "workspace",
    "lti",
    "assignment",
]

MIDDLEWARE = [
    "vcl.middlewares.HealthCheckMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "lti.middleware.SameSiteMiddleware",
    "vcl_utils.logging.CaptureWorkspaceSessionMiddleware",
]

ROOT_URLCONF = "vcl.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "lti", "templates"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "vcl.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
DATABASES = {
    "default": dict(
        env.db("DB"),
        OPTIONS={
            "connect_timeout": 120,
        },
    )
}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

DATABASES = {"default": dict(env.db("DB"), OPTIONS={"connect_timeout": 5})}


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_ROOT = "static/"
STATIC_URL = "web-static/"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Debug Toolbar
INTERNAL_IPS = [
    "127.0.0.1",
]
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda __: DEBUG,
}

# DRF
REST_FRAMEWORK = {
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
}

# RabbitMQ
RABBITMQ_CREDENTIALS = env.list("RABBITMQ_CREDENTIALS")
RABBITMQ_URL = env.list("RABBITMQ_URL")

# Redis / Cache / Celery
REDIS_HOST = env("REDIS_HOST", default="redis")
REDIS_PORT = env("REDIS_PORT", default="6379")
REDIS_CELERY_DB_INDEX = env("REDIS_CELERY_DB_INDEX", default="0")
REDIS_CACHE_DB_INDEX = env("REDIS_CACHE_DB_INDEX", default="1")

CELERY_RESULT_BACKEND = "django-db"
CELERYD_TASK_SOFT_TIME_LIMIT = 600  # 5 minutes
CORS_ALLOWED_ORIGINS = [f"{INGRESS_PROTOCOL}://{INGRESS_HOST}"]

BROKER_URL = "redis://{host}:{port}/{db_index}".format(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db_index=REDIS_CELERY_DB_INDEX,
)

CACHE_PREFIX = "vcl_cache"
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CACHE_DB_INDEX}",
        "TIMEOUT": None,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": CACHE_PREFIX,
    },
}

# App settings
ENABLE_CELERY_PERIODIC_TASKS = env("ENABLE_CELERY_PERIODIC_TASKS", default=True)

SESSION_COOKIE_NAME = "sessionid"
SESSION_COOKIE_SAMESITE = None  # should be set as 'None' for Django >= 3.1
SESSION_COOKIE_SECURE = False  # should be True in case of HTTPS usage (production)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Whitenoise caching
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

LOGGING = get_logging_config(app_name="web", include_ws_session=True)