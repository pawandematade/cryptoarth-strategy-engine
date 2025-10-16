#!/bin/bash

# Define log files
BEAT_LOGFILE=/var/log/celery/beat.log


# Ensure the log directory exists
mkdir -p /var/log/celery
touch $BEAT_LOGFILE
# Stop any existing Celery beat and worker processes
pkill -f 'celery -A delta_backend worker'
pkill -f 'celery -A delta_backend beat'

# Start Celery Beat
# celery -A dematade beat --loglevel=info --logfile=$BEAT_LOGFILE --detach

# Start Celery Worker

celery -A delta_backend beat --loglevel=info --logfile=$BEAT_LOGFILE --detach

# Optional: Run the Python server
# export DJANGO_SETTINGS_MODULE=dematade.settings
# gunicorn dematade.asgi:application -w 40 --threads 40 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
# daphne -b 0.0.0.0 -p 8000 --workers 4 dematade.asgi:application

# Monitor the log files
tail -f $BEAT_LOGFILE 