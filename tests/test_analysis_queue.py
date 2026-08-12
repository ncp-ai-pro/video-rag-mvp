import json

import pytest

from app import analysis_queue, config


def test_priority_values_map_named_priorities():
    assert analysis_queue.priority_values("ultra") == {"rabbitmq": 9, "database": 0}
    assert analysis_queue.priority_values("manual") == {"rabbitmq": 7, "database": 50}
    assert analysis_queue.priority_values("normal") == {"rabbitmq": 4, "database": 100}
    assert analysis_queue.priority_values("bulk") == {"rabbitmq": 1, "database": 500}


def test_priority_values_reject_unknown_name():
    with pytest.raises(ValueError, match="unknown analysis priority"):
        analysis_queue.priority_values("urgent")


@pytest.mark.parametrize("provider", ["disabled", "postgres"])
def test_publish_is_noop_for_database_queue_providers(monkeypatch, provider):
    monkeypatch.setattr(config, "ANALYSIS_QUEUE_PROVIDER", provider, raising=False)
    monkeypatch.setattr(analysis_queue, "pika", None)

    assert analysis_queue.publish_analysis_job(4, "analyze_video", "normal", "job-4") is False


def test_rabbitmq_publish_declares_durable_priority_queue(monkeypatch):
    events = []

    class FakeChannel:
        def queue_declare(self, **kwargs):
            events.append(("queue_declare", kwargs))

        def basic_publish(self, **kwargs):
            events.append(("basic_publish", kwargs))

    class FakeConnection:
        def __init__(self, parameters):
            events.append(("connection", parameters))

        def channel(self):
            return FakeChannel()

        def close(self):
            events.append(("close", None))

    class FakePika:
        @staticmethod
        def URLParameters(url):
            return {"url": url}

        BlockingConnection = FakeConnection

        class BasicProperties:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

    monkeypatch.setattr(config, "ANALYSIS_QUEUE_PROVIDER", "rabbitmq", raising=False)
    monkeypatch.setattr(config, "RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F", raising=False)
    monkeypatch.setattr(analysis_queue, "pika", FakePika)

    assert analysis_queue.publish_analysis_job(8, "analyze_video", "manual", "analysis-8") is True

    assert events[0] == ("connection", {"url": "amqp://guest:guest@rabbitmq:5672/%2F"})
    assert events[1] == (
        "queue_declare",
        {"queue": "analysis.jobs", "durable": True, "arguments": {"x-max-priority": 10}},
    )
    published = events[2][1]
    assert published["exchange"] == ""
    assert published["routing_key"] == "analysis.jobs"
    assert published["properties"].kwargs == {"delivery_mode": 2, "priority": 7}
    assert json.loads(published["body"]) == {
        "job_id": 8,
        "kind": "analyze_video",
        "priority": "manual",
        "idempotency_key": "analysis-8",
    }
    assert events[3] == ("close", None)


def test_rabbitmq_mode_requires_pika(monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_QUEUE_PROVIDER", "rabbitmq", raising=False)
    monkeypatch.setattr(analysis_queue, "pika", None)

    with pytest.raises(RuntimeError, match="pika is required"):
        analysis_queue.publish_analysis_job(4, "analyze_video", "normal", "job-4")


def test_unknown_queue_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_QUEUE_PROVIDER", "sqs", raising=False)

    with pytest.raises(ValueError, match="unknown analysis queue provider"):
        analysis_queue.publish_analysis_job(4, "analyze_video", "normal", "job-4")
