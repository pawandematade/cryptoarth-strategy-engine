#!/bin/bash

pkill -f 'celery -A delta_backend worker'
pkill -f 'celery -A delta_backend beat'
export DJANGO_SETTINGS_MODULE=delta_backend.settings


# gunicorn dematade.asgi:application -w 4 --threads 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

gunicorn delta_backend.asgi:application \
  -w 4 \
  --threads 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  # --bind 0.0.0.0:8443 \
  # --certfile /etc/ssl/certs/tradearth.pem \
  # --keyfile /etc/ssl/certs/tradearth.key
