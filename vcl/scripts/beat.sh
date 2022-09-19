#!/usr/bin/env bash
celery -A vcl beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
