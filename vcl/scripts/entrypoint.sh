#!/usr/bin/env bash
python manage.py collectstatic --no-input
# this magic command will run Dockerfile's command:
exec "$@"
