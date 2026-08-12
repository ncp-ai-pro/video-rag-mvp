"""Optional RabbitMQ publisher for analysis jobs.

The database remains the source of truth for queued jobs.  This module only
notifies a RabbitMQ consumer when ``ANALYSIS_QUEUE_PROVIDER=rabbitmq``.
"""
import json
from typing import Mapping, Optional

from . import config

try:  # pika is deliberately optional for the local/PostgreSQL worker path.
    import pika
except ImportError:  # pragma: no cover - exercised through module monkeypatching
    pika = None


QUEUE_NAME = "analysis.jobs"
QUEUE_ARGUMENTS = {"x-max-priority": 10}
RABBITMQ_PRIORITIES = {"ultra": 9, "manual": 7, "normal": 4, "bulk": 1}
DATABASE_PRIORITIES = {"ultra": 0, "manual": 50, "normal": 100, "bulk": 500}
_NOOP_PROVIDERS = {"disabled", "postgres"}


def priority_values(priority: str) -> Mapping[str, int]:
    """Return the RabbitMQ and database priority values for a named priority."""
    normalized = priority.strip().lower()
    if normalized not in RABBITMQ_PRIORITIES:
        raise ValueError(f"unknown analysis priority: {priority}")
    return {
        "rabbitmq": RABBITMQ_PRIORITIES[normalized],
        "database": DATABASE_PRIORITIES[normalized],
    }


def _queue_provider() -> str:
    return getattr(config, "ANALYSIS_QUEUE_PROVIDER", "postgres").strip().lower()


def _rabbitmq_url() -> str:
    return getattr(config, "RABBITMQ_URL", "").strip()


def publish_analysis_job(
    job_id: int,
    kind: str,
    priority: str,
    idempotency_key: str,
) -> bool:
    """Publish a job notification, returning False for DB-only queue providers.

    RabbitMQ configuration and connection errors intentionally propagate when
    RabbitMQ is selected, so callers do not silently lose a wake-up signal.
    """
    provider = _queue_provider()
    if provider in _NOOP_PROVIDERS:
        return False
    if provider != "rabbitmq":
        raise ValueError(f"unknown analysis queue provider: {provider}")
    if pika is None:
        raise RuntimeError("pika is required when ANALYSIS_QUEUE_PROVIDER=rabbitmq")

    normalized_priority = priority.strip().lower()
    values = priority_values(normalized_priority)
    payload = json.dumps(
        {
            "job_id": job_id,
            "kind": kind,
            "priority": normalized_priority,
            "idempotency_key": idempotency_key,
        }
    )
    parameters = pika.URLParameters(_rabbitmq_url())
    connection = pika.BlockingConnection(parameters)
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments=QUEUE_ARGUMENTS)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=payload,
            properties=pika.BasicProperties(delivery_mode=2, priority=values["rabbitmq"]),
        )
    finally:
        connection.close()
    return True
