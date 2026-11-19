"""Celery configuration for ID-only, PostgreSQL-backed analysis jobs."""

import ssl

from celery import Celery
from dotenv import load_dotenv

from app.config import get_settings

load_dotenv(override=False)
settings = get_settings()

celery_app = Celery(
    "docguard",
    broker=settings.celery_broker_url,
    include=["app.tasks.analysis_jobs"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=5,
    broker_transport_options={
        "visibility_timeout": max(3600, settings.analysis_timeout_seconds * 2)
    },
    task_soft_time_limit=settings.analysis_timeout_seconds + 30,
    task_time_limit=settings.analysis_timeout_seconds + 60,
    beat_schedule={
        "maintain-analysis-jobs": {
            "task": "app.tasks.analysis_jobs.maintain_analysis_jobs",
            "schedule": 15.0,
        }
    },
)
if settings.celery_broker_url.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
