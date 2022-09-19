#!/usr/bin/env bash
pip install --disable-pip-version-check --exists-action w -r requirements/core.txt
celery -A vcl worker --concurrency=3 -Ofair -E -l info
