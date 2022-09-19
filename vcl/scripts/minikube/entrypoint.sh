#!/usr/bin/env bash
# Most likely `pip install` and migrations should be run in initContainer
pip install --disable-pip-version-check --exists-action w -r requirements/core.txt
python manage.py migrate --no-input
python manage.py collectstatic --no-input
# this magic command will run Dockerfile's command:
exec "$@"
