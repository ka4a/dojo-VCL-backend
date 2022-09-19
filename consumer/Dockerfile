FROM python:3.9-slim-buster

ENV PYTHONUNBUFFERED 1
ENV APP /var/www/consumer
ENV UTILS_PKG /var/www/vcl-utils

WORKDIR $APP

ADD consumer/ $APP
ADD vcl-utils/ $UTILS_PKG

# Install system requirements
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt install -y gcc python3-dev build-essential g++ procps --fix-missing \
    && pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R www-data:www-data /var/www \
    && pip install --disable-pip-version-check --exists-action w -r requirements.txt \
    && pip install -e $UTILS_PKG

USER www-data
