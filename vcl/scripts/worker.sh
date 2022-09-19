#!/usr/bin/env bash
celery -A vcl worker --concurrency=3 -Ofair -E -l info
