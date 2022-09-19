#!/usr/bin/env bash
pip install --disable-pip-version-check --exists-action w -r requirements/core.txt
celery -A vcl beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
