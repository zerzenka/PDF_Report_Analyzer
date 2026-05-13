"""
Celery application — worker: celery -A config worker --loglevel=info
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "scan-watch-folder": {
        "task": "apps.documents.tasks.scan_watch_folder",
        "schedule": 300.0,  # every 5 minutes
    },
    "sync-employees": {
        "task": "apps.documents.tasks.sync_employees_from_source_db",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),  # Monday 6am
    },
}
