FROM python:3.9-slim-buster

ENV PYTHONUNBUFFERED 1
ENV APP /init-container
ENV UTILS_PKG /vcl-utils

WORKDIR $APP

ADD init-container/ $APP
ADD vcl-utils/ $UTILS_PKG

# Install system requirements
RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt install -y git --fix-missing \
    && pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --disable-pip-version-check --exists-action w -r requirements.txt \
    && pip install $UTILS_PKG
