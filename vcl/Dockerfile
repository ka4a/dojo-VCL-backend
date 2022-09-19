FROM python:3.9-slim-buster

ENV PYTHONUNBUFFERED 1

ENV APP /var/www/vcl
ENV UTILS_PKG /var/www/vcl-utils

WORKDIR $APP

ADD vcl/ $APP

ADD vcl-utils/ $UTILS_PKG

# Install system requirements
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt install -y libpq-dev gcc python3-dev build-essential git g++ procps --fix-missing \
    && pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R www-data:www-data /var/www \
    && pip install --disable-pip-version-check --exists-action w -r requirements/core.txt -r requirements/dev.txt \
    && pip install -e $UTILS_PKG

USER www-data
