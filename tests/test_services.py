import importlib
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_metadata_recommendation_and_timestamped_rag():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "test.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"

        from app import config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        with db.connection() as conn:
            channel_id = conn.execute(
                "INSERT INTO channels(user_id, url, name) VALUES (?, ?, ?) RETURNING id",
                (workspace["id"], "https://www.youtube.com/@example", "example"),
            ).fetchone()["id"]

        video_id = services.upsert_video(
            channel_id,
            {
                "platform_video_id": "abc123",
                "title": "FastAPI로 RAG 챗봇 만들기",
                "description": "벡터 검색과 자막 기반 답변을 설명합니다.",
                "url": "https://www.youtube.com/watch?v=abc123",
            },
        )
        services.import_transcript(
            video_id,
            [{"start_seconds": 12, "end_seconds": 28, "text": "RAG는 검색한 자막 근거를 모델에 전달합니다."}],
        )

        recommendations = services.find_metadata(workspace["id"], "RAG 챗봇", 5)
        evidence = services.find_evidence(workspace["id"], "자막 근거", 3)
        assert recommendations[0]["video_id"] == video_id
        assert evidence[0]["start_seconds"] == 12
        assert evidence[0]["url"].endswith("t=12s")


def test_paragraph_context_groups_multiple_rag_chunks():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "paragraph.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"

        from app import config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        with db.connection() as conn:
            channel_id = conn.execute(
                "INSERT INTO channels(user_id, url, name) VALUES (?, ?, ?) RETURNING id",
                (workspace["id"], "https://www.youtube.com/@paragraph", "paragraph"),
            ).fetchone()["id"]

        video_id = services.upsert_video(
            channel_id,
            {
                "platform_video_id": "paragraph123",
                "title": "문단 RAG 테스트",
                "description": "문단과 작은 청크를 분리합니다.",
                "url": "https://www.youtube.com/watch?v=paragraph123",
            },
        )
        services.import_transcript(
            video_id,
            [
                {
                    "paragraph_index": 0,
                    "chunk_index": 0,
                    "start_seconds": 10,
                    "end_seconds": 20,
                    "text": "RAG 검색은 작은 청크를 기준으로 수행합니다.",
                },
                {
                    "paragraph_index": 0,
                    "chunk_index": 1,
                    "start_seconds": 20,
                    "end_seconds": 30,
                    "text": "답변 컨텍스트는 같은 문단으로 확장합니다.",
                },
            ],
            paragraphs=[
                {
                    "paragraph_index": 0,
                    "start_seconds": 10,
                    "end_seconds": 30,
                    "text": "RAG 검색은 작은 청크를 기준으로 수행합니다. 답변 컨텍스트는 같은 문단으로 확장합니다.",
                }
            ],
        )

        evidence = services.find_evidence(workspace["id"], "RAG 검색 문단 컨텍스트", 3, video_id)
        assert len(evidence) == 1
        assert evidence[0]["paragraph_id"] is not None
        assert evidence[0]["quote"] != evidence[0]["context"]
        assert "답변 컨텍스트" in evidence[0]["context"]


def test_ultra_evidence_mode_uses_sentence_embedding_similarity():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "ultra.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"

        from app import config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        with db.connection() as conn:
            channel_id = conn.execute(
                "INSERT INTO channels(user_id, url, name) VALUES (?, ?, ?) RETURNING id",
                (workspace["id"], "https://www.youtube.com/@ultra", "ultra"),
            ).fetchone()["id"]
        video_id = services.upsert_video(
            channel_id,
            {
                "platform_video_id": "ultra123",
                "title": "울트라 근거 테스트",
                "description": "문장 embedding으로 근거를 고릅니다.",
                "url": "https://www.youtube.com/watch?v=ultra123",
            },
        )
        services.import_transcript(
            video_id,
            [
                {
                    "start_seconds": 1,
                    "end_seconds": 20,
                    "text": "잡담입니다. RAG 구축은 자막을 청크로 나누고 embedding을 저장하는 순서입니다.",
                }
            ],
        )

        evidence = services.find_evidence(workspace["id"], "RAG 구축 embedding 순서", 3, video_id, "ultra")

        assert evidence[0]["highlight"]["method"] == "sentence_embedding_similarity"
        assert "RAG 구축" in evidence[0]["highlight"]["text"]
def test_collect_channel_metadata_accepts_single_video_url(monkeypatch):
    from app import services

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "id": "eOqXQqg0_Dw",
                    "title": "단일 영상 메타데이터",
                    "description": "채널 칸에 영상 URL을 넣어도 메타데이터를 수집합니다.",
                    "webpage_url": "https://www.youtube.com/watch?v=eOqXQqg0_Dw",
                    "duration": 123,
                    "upload_date": "20260808",
                }
            ),
            "",
        )

    monkeypatch.setattr(services.subprocess, "run", fake_run)

    videos = services.collect_channel_metadata("https://www.youtube.com/watch?v=eOqXQqg0_Dw")

    assert commands[0][1:4] == ["--dump-single-json", "--skip-download", "--no-playlist"]
    assert videos == [
        {
            "platform_video_id": "eOqXQqg0_Dw",
            "title": "단일 영상 메타데이터",
            "description": "채널 칸에 영상 URL을 넣어도 메타데이터를 수집합니다.",
            "url": "https://www.youtube.com/watch?v=eOqXQqg0_Dw",
            "thumbnail_url": None,
            "duration_seconds": 123,
            "uploaded_at": "20260808",
        }
    ]


def test_collect_channel_metadata_keeps_flat_playlist_for_channel_urls(monkeypatch):
    from app import services

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(
                [
                    json.dumps({"id": "video1", "title": "첫 영상"}),
                    json.dumps({"id": "video2", "title": "둘째 영상"}),
                ]
            ),
            "",
        )

    monkeypatch.setattr(services.subprocess, "run", fake_run)

    videos = services.collect_channel_metadata("https://www.youtube.com/@example")

    assert commands[0][1:4] == ["--flat-playlist", "--dump-json", "--skip-download"]
    assert [video["platform_video_id"] for video in videos] == ["video1", "video2"]


def test_guest_workspace_is_restored_or_connected_by_code():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "workspace.db")
        from app import config, db, main, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        importlib.reload(main)

        with TestClient(main.app) as first_browser:
            first_workspace = first_browser.get("/auth/me").json()
            assert first_browser.get("/auth/me").json()["workspace_code"] == first_workspace["workspace_code"]
            origin = "http://localhost:5173"
            preflight = first_browser.options(
                "/chat",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == origin
            assert preflight.headers["access-control-allow-credentials"] == "true"

        with TestClient(main.app) as second_browser:
            second_workspace = second_browser.get("/auth/me").json()
            assert second_workspace["workspace_code"] != first_workspace["workspace_code"]
            connected = second_browser.post("/auth/workspace", json={"workspace_code": first_workspace["workspace_code"]})
            assert connected.status_code == 200
            assert second_browser.get("/auth/me").json()["workspace_code"] == first_workspace["workspace_code"]


def test_recent_chat_history_uses_cache_hit(monkeypatch):
    from app import services

    cached = [{"role": "user", "content": "캐시 질문"}, {"role": "assistant", "content": "캐시 답변"}]
    monkeypatch.setattr(services.chat_cache, "get_recent", lambda *args, **kwargs: cached)

    def fail_connection():
        raise AssertionError("PostgreSQL should not be queried on a cache hit")

    monkeypatch.setattr(services, "connection", fail_connection)

    assert services.recent_chat_history(42) == cached


def test_recent_chat_history_populates_cache_on_miss(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "chat-cache-miss.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        from app import config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        captured = {}
        monkeypatch.setattr(services.chat_cache, "get_recent", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            services.chat_cache,
            "set_recent",
            lambda user_id, messages: captured.update({"user_id": user_id, "messages": messages}),
        )

        services.record_chat_message(workspace["id"], "user", "DB 질문")
        services.record_chat_message(workspace["id"], "assistant", "DB 답변")
        history = services.recent_chat_history(workspace["id"])

        assert history == [{"role": "user", "content": "DB 질문"}, {"role": "assistant", "content": "DB 답변"}]
        assert captured == {"user_id": workspace["id"], "messages": history}


def test_recent_chat_history_with_evidence_bypasses_cache(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "chat-cache-evidence.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        from app import config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        services.record_chat_message(workspace["id"], "assistant", "근거 답변", [{"video_id": 1}])

        def fail_cache(*args, **kwargs):
            raise AssertionError("evidence history should read PostgreSQL, not Redis cache")

        monkeypatch.setattr(services.chat_cache, "get_recent", fail_cache)
        monkeypatch.setattr(services.chat_cache, "set_recent", fail_cache)

        assert services.recent_chat_history(workspace["id"], include_evidence=True) == [
            {"role": "assistant", "content": "근거 답변", "evidence": [{"video_id": 1}]}
        ]


def test_record_chat_message_updates_cache_after_postgres_write(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "chat-cache-append.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        os.environ["CHAT_HISTORY_TURNS"] = "3"
        from app import config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        appended = []
        monkeypatch.setattr(services.chat_cache, "append_recent", lambda *args, **kwargs: appended.append((args, kwargs)))

        services.record_chat_message(workspace["id"], "assistant", "답변", [{"video_id": 1}])

        assert appended == [
            (
                (workspace["id"], {"role": "assistant", "content": "답변", "evidence": [{"video_id": 1}]}),
                {"max_messages": 6},
            )
        ]


def test_recent_chat_history_falls_back_when_cache_fails(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "chat-cache-fallback.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        from app import chat_cache, config, db, services, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(chat_cache)
        importlib.reload(services)
        importlib.reload(workspaces)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        services.record_chat_message(workspace["id"], "user", "fallback 질문")

        class BrokenRedis:
            def lrange(self, *args, **kwargs):
                raise RuntimeError("redis down")

        monkeypatch.setattr(chat_cache, "_redis_client", lambda: BrokenRedis())

        assert services.recent_chat_history(workspace["id"]) == [{"role": "user", "content": "fallback 질문"}]


def test_chat_router_keeps_post_contract_and_workspace_scope():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "chat.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        from app import chat_main, config, db, dependencies, main, services, web, workspaces
        from app.routers import chat

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        importlib.reload(dependencies)
        importlib.reload(chat)
        importlib.reload(web)
        importlib.reload(main)
        importlib.reload(chat_main)

        assert not any(route.path == "/chat" and "POST" in route.methods for route in main.app.routes)
        assert any(route.path == "/chat" and "POST" in route.methods for route in chat_main.app.routes)

        with TestClient(main.app) as owner, TestClient(chat_main.app) as owner_chat:
            channel = owner.post(
                "/channels",
                json={"url": "https://www.youtube.com/@chat-example", "name": "chat example"},
            ).json()
            video = owner.post(
                f"/channels/{channel['id']}/videos",
                json={
                    "platform_video_id": "chat123",
                    "title": "RAG 채팅 테스트 영상",
                    "url": "https://www.youtube.com/watch?v=chat123",
                },
            ).json()
            transcript = owner.post(
                f"/videos/{video['video_id']}/transcript",
                json={
                    "segments": [
                        {
                            "start_seconds": 12,
                            "end_seconds": 25,
                            "text": "채팅은 검색한 자막 근거로 답변합니다.",
                        }
                    ]
                },
            )
            assert transcript.status_code == 204

            owner_chat.cookies.set("video_rag_session", owner.cookies.get("video_rag_session"))
            response = owner_chat.post("/chat", json={"query": "자막 근거", "video_id": video["video_id"]})
            assert response.status_code == 200
            assert set(response.json()) == {"answer", "evidence"}
            assert response.json()["evidence"][0]["video_id"] == video["video_id"]
            assert response.json()["evidence"][0]["rank"] == 1
            assert response.json()["evidence"][0]["is_primary"] is True
            assert "highlight" not in response.json()["evidence"][0]
            global_history = owner_chat.get("/chat/history")
            assert global_history.status_code == 200
            assert global_history.json()["messages"] == []
            history = owner_chat.get(f"/chat/history?video_id={video['video_id']}")
            assert history.status_code == 200
            messages = history.json()["messages"]
            assert [message["role"] for message in messages] == ["user", "assistant"]
            assert [message["video_id"] for message in messages] == [video["video_id"], video["video_id"]]
            assert messages[0]["content"] == "자막 근거"
            assert messages[1]["evidence"][0]["video_id"] == video["video_id"]
            assert messages[1]["evidence"][0]["is_primary"] is True

            with owner_chat.stream(
                "POST",
                "/chat/stream",
                json={"query": "자막 근거", "video_id": video["video_id"], "evidence_mode": "precise"},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                streamed = response.read().decode("utf-8")
            assert streamed.startswith("retry: 3000")
            assert "event: evidence" in streamed
            assert "event: token" in streamed
            assert "event: done" in streamed
            assert '"text":"로컬 "' in streamed
            assert '"text":"테스트 "' in streamed
            assert '"method":"query_token_overlap"' in streamed
            history = owner_chat.get(f"/chat/history?video_id={video['video_id']}")
            assert history.status_code == 200
            messages = history.json()["messages"]
            assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]
            assert {message["video_id"] for message in messages} == {video["video_id"]}
            assert messages[-1]["evidence"][0]["video_id"] == video["video_id"]
            assert messages[-1]["evidence"][0]["highlight"]["text"] == "채팅은 검색한 자막 근거로 답변합니다."
            latest_page = owner_chat.get(f"/chat/history?limit=2&video_id={video['video_id']}")
            assert latest_page.status_code == 200
            latest_body = latest_page.json()
            assert [message["role"] for message in latest_body["items"]] == ["user", "assistant"]
            assert latest_body["has_more"] is True
            previous_page = owner_chat.get(
                f"/chat/history?limit=2&video_id={video['video_id']}&before_id={latest_body['next_cursor']}"
            )
            assert previous_page.status_code == 200
            previous_body = previous_page.json()
            assert [message["role"] for message in previous_body["items"]] == ["user", "assistant"]
            assert previous_body["has_more"] is False

        with TestClient(main.app) as other_workspace, TestClient(chat_main.app) as other_workspace_chat:
            assert other_workspace.get(f"/videos/{video['video_id']}").status_code == 404
            assert other_workspace_chat.post(
                "/chat", json={"query": "자막 근거", "video_id": video["video_id"]}
            ).status_code == 404
            assert other_workspace_chat.get(f"/chat/history?video_id={video['video_id']}").status_code == 404
            response = other_workspace_chat.post("/chat", json={"query": "자막 근거"})
            assert response.status_code == 200
            assert response.json()["evidence"] == []
            history = other_workspace_chat.get("/chat/history")
            assert history.status_code == 200
            messages = history.json()["messages"]
            assert messages[-1]["evidence"] == []


def test_sse_streams_db_owned_analysis_progress_and_rejects_other_workspace():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "events.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        from app import config, db, main, services, worker, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        importlib.reload(worker)
        importlib.reload(main)
        main.SSE_POLL_INTERVAL_SECONDS = 0.02
        main.SSE_HEARTBEAT_SECONDS = 0.04

        with TestClient(main.app) as owner:
            channel = owner.post(
                "/channels",
                json={"url": "https://www.youtube.com/@example", "name": "example"},
            ).json()
            video = owner.post(
                f"/channels/{channel['id']}/videos",
                json={
                    "platform_video_id": "events123",
                    "title": "SSE 테스트 영상",
                    "url": "https://www.youtube.com/watch?v=events123",
                },
            ).json()
            queued = owner.post(f"/videos/{video['video_id']}/analyze")
            assert queued.status_code == 202
            assert owner.post(f"/videos/{video['video_id']}/analyze").status_code == 409

            def advance_worker_state():
                time.sleep(0.15)
                job = worker.claim_job()
                time.sleep(0.08)
                services.update_analysis_progress(job["id"], video["video_id"], "embedding")
                time.sleep(0.08)
                services.finish_analysis(job["id"], video["video_id"])

            thread = threading.Thread(target=advance_worker_state)
            thread.start()
            with owner.stream("GET", f"/videos/{video['video_id']}/events") as response:
                assert response.status_code == 200
                body = response.read().decode("utf-8")
            thread.join(timeout=2)
            completed_video = owner.get(f"/videos/{video['video_id']}").json()
            assert completed_video["analysis_status"] == "succeeded"
            assert completed_video["analysis_stage"] == "completed"

            failed_video = owner.post(
                f"/channels/{channel['id']}/videos",
                json={
                    "platform_video_id": "failure123",
                    "title": "실패 SSE 테스트 영상",
                    "url": "https://www.youtube.com/watch?v=failure123",
                },
            ).json()
            failed_job = owner.post(f"/videos/{failed_video['video_id']}/analyze").json()
            services.finish_analysis(failed_job["job_id"], failed_video["video_id"], "subtitle_not_found")
            with owner.stream("GET", f"/videos/{failed_video['video_id']}/events") as response:
                assert response.status_code == 200
                failed_body = response.read().decode("utf-8")
            failed_video_state = owner.get(f"/videos/{failed_video['video_id']}").json()
            assert failed_video_state["analysis_status"] == "failed"
            assert failed_video_state["analysis_stage"] == "failed"

        events = [
            json.loads(part.split("data: ", 1)[1].split("\n", 1)[0])
            for part in body.split("event: analysis_status\n")
            if "data: " in part
        ]
        assert body.startswith("retry: 3000")
        assert ": heartbeat\n\n" in body
        assert [event["progress"]["stage"] for event in events] == [
            "queued",
            "downloading_caption",
            "embedding",
            "completed",
        ]
        assert events[-1]["status"] == "succeeded"
        assert events[-1]["error"] is None
        assert events[-1]["updated_at"].endswith("Z")
        failed_event = json.loads(failed_body.split("data: ", 1)[1])
        assert failed_event["status"] == "failed"
        assert failed_event["progress"]["stage"] == "failed"
        assert failed_event["error"] == "subtitle_not_found"

        with TestClient(main.app) as other_workspace:
            forbidden = other_workspace.get(f"/videos/{video['video_id']}/events")
            assert forbidden.status_code == 404


def test_clova_speech_segments_use_seconds_and_domain_relative_object_key(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_STT_INPUT_PREFIX", "clova-speech/input")
    from app import config, services

    importlib.reload(config)
    importlib.reload(services)

    assert services.speech_data_key(
        "clova-speech/input/videos/12/revisions/314/source.m4a"
    ) == "/videos/12/revisions/314/source.m4a"
    assert services.normalize_clova_speech_segments(
        {
            "segments": [
                {"start": 1250, "end": 3875, "text": "  첫 번째   자막입니다.  "},
                {"start": 5000, "end": 5000, "text": "버려야 할 구간"},
            ]
        }
    ) == [{"start_seconds": 1.25, "end_seconds": 3.875, "text": "첫 번째 자막입니다."}]
    with pytest.raises(ValueError, match="speech input object"):
        services.speech_data_key("videos/12/source.m4a")


def test_youtube_vtt_parser_ignores_cue_settings_and_markup(tmp_path):
    from app.worker import parse_vtt

    subtitle = tmp_path / "youtube.vtt"
    subtitle.write_text(
        """WEBVTT

00:00:01.120 --> 00:00:04.590 align:start position:0%
안녕하세요.<00:00:01.800><c> 개발자입니다.</c>

""",
        encoding="utf-8",
    )

    assert parse_vtt(subtitle) == [
        {"start_seconds": 1.12, "end_seconds": 4.59, "text": "안녕하세요. 개발자입니다."}
    ]


def test_worker_merges_rolling_captions_into_bounded_rag_chunks(monkeypatch):
    monkeypatch.setenv("WORKER_RAG_CHUNK_MAX_SECONDS", "60")
    monkeypatch.setenv("WORKER_RAG_CHUNK_MAX_CHARS", "100")
    from app import config, worker

    importlib.reload(config)
    importlib.reload(worker)

    chunks = worker.build_rag_chunks(
        [
            {"start_seconds": 0, "end_seconds": 3, "text": "첫 번째 문장"},
            {"start_seconds": 3, "end_seconds": 6, "text": "첫 번째 문장 두 번째 문장"},
            {"start_seconds": 6, "end_seconds": 9, "text": "두 번째 문장 세 번째 문장"},
        ]
    )

    assert chunks == [{"start_seconds": 0.0, "end_seconds": 9.0, "text": "첫 번째 문장 두 번째 문장 세 번째 문장"}]


def test_embedding_rate_limiter_retries_429_using_reset_header(monkeypatch):
    from app import services

    monkeypatch.setenv("EMBEDDING_PROVIDER", "clova")
    from app import config

    importlib.reload(config)
    importlib.reload(services)
    calls, sleeps = [], []

    def request_embedding(text):
        calls.append(text)
        if len(calls) == 1:
            request = __import__("httpx").Request("POST", "https://example.test/embedding")
            response = __import__("httpx").Response(
                429, request=request, headers={"x-ratelimit-reset-requests": "3s"}
            )
            raise __import__("httpx").HTTPStatusError("rate limited", request=request, response=response)
        return [1.0, 0.0]

    limiter = services.EmbeddingRateLimiter(
        min_interval_seconds=1.5,
        max_retries=5,
        backoff_base_seconds=2,
        request_embedding=request_embedding,
        clock=lambda: 0.0,
        sleep=sleeps.append,
    )
    assert limiter.embed("자막") == [1.0, 0.0]
    assert calls == ["자막", "자막"]
    assert sleeps == [3.0]


def test_clova_speech_uses_domain_relative_storage_key_and_secret_header(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_STT_INPUT_PREFIX", "clova-speech/input")
    monkeypatch.setenv("CLOVA_SPEECH_INVOKE_URL", "https://speech.example/invoke")
    monkeypatch.setenv("CLOVA_SPEECH_API_KEY", "speech-test-secret")
    from app import config, services

    importlib.reload(config)
    importlib.reload(services)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"result": "SUCCEEDED", "segments": [{"start": 0, "end": 1000, "text": "완료"}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(services.httpx, "post", fake_post)
    response = services.transcribe_object_storage("clova-speech/input/videos/12/source.m4a")

    assert response["result"] == "SUCCEEDED"
    assert captured["url"] == "https://speech.example/invoke/recognizer/object-storage"
    assert captured["headers"]["X-CLOVASPEECH-API-KEY"] == "speech-test-secret"
    assert captured["json"]["dataKey"] == "/videos/12/source.m4a"
    assert captured["json"]["completion"] == "sync"


def test_worker_falls_back_to_clova_speech_and_reuses_transcript_import(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        monkeypatch.setenv("DATABASE_PATH", os.path.join(directory, "speech.db"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("CHAT_PROVIDER", "mock")
        from app import config, db, services, worker, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        importlib.reload(worker)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        with db.connection() as conn:
            channel_id = conn.execute(
                "INSERT INTO channels(user_id, url, name) VALUES (?, ?, ?) RETURNING id",
                (workspace["id"], "https://www.youtube.com/@speech-example", "speech example"),
            ).fetchone()["id"]
        video_id = services.upsert_video(
            channel_id,
            {
                "platform_video_id": "speech123",
                "title": "자막 없는 STT 테스트 영상",
                "description": "",
                "url": "https://www.youtube.com/watch?v=speech123",
            },
        )
        job_id = services.enqueue_analysis(video_id)

        audio_path = config.DATA_DIR / "downloads" / str(video_id) / "source.m4a"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"audio")
        uploaded_files, uploaded_json, normalized = [], [], []
        monkeypatch.setattr(
            worker.subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
        )
        monkeypatch.setattr(worker, "download_audio", lambda *_: audio_path)
        monkeypatch.setattr(worker, "object_storage_is_configured", lambda: True)
        monkeypatch.setattr(
            worker,
            "upload_artifact_file",
            lambda path, key, content_type=None: uploaded_files.append((path, key, content_type)) or key,
        )
        monkeypatch.setattr(
            worker,
            "upload_artifact_json",
            lambda payload, key: uploaded_json.append((payload, key)) or key,
        )
        monkeypatch.setattr(
            worker,
            "transcribe_object_storage",
            lambda key: {"result": "SUCCEEDED", "segments": [{"start": 2000, "end": 4500, "text": "STT 결과입니다."}]},
        )
        monkeypatch.setattr(
            worker,
            "store_normalized_transcript",
            lambda *args: normalized.append(args) or "videos/12/transcript.normalized.v1.json",
        )

        worker.analyze_video(job_id, video_id)

        assert uploaded_files[0][1].endswith("/source.m4a")
        assert uploaded_json[0][1].endswith("/result.raw.json")
        assert normalized[0][2] == "clova_speech"
        with db.connection() as conn:
            chunk = conn.execute(
                "SELECT start_seconds, end_seconds, text FROM transcript_chunks WHERE video_id=?",
                (video_id,),
            ).fetchone()
            artifacts = conn.execute(
                "SELECT kind, object_key FROM analysis_artifacts WHERE video_id=? ORDER BY kind",
                (video_id,),
            ).fetchall()
        assert dict(chunk) == {"start_seconds": 2.0, "end_seconds": 4.5, "text": "STT 결과입니다."}
        assert {row["kind"] for row in artifacts} == {"source_audio", "speech_raw_result"}


def test_worker_falls_back_only_when_yt_dlp_reports_no_subtitles(monkeypatch):
    from app import worker

    with tempfile.TemporaryDirectory() as directory:
        output_dir = Path(directory)
        no_subtitles = subprocess.CompletedProcess(
            ["yt-dlp"], 1, "", "ERROR: There are no subtitles for the requested languages"
        )
        monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: no_subtitles)
        assert worker.download_subtitles("https://www.youtube.com/watch?v=no-captions", output_dir) is None


def test_worker_claims_higher_priority_job_first(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        monkeypatch.setenv("DATABASE_PATH", os.path.join(directory, "priority.db"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("CHAT_PROVIDER", "mock")

        from app import config, db, services, worker, workspaces

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        importlib.reload(worker)
        db.initialize()
        workspace = workspaces.create_guest_workspace()
        with db.connection() as conn:
            channel_id = conn.execute(
                "INSERT INTO channels(user_id, url, name) VALUES (?, ?, ?) RETURNING id",
                (workspace["id"], "https://www.youtube.com/@priority", "priority"),
            ).fetchone()["id"]
        low_video_id = services.upsert_video(
            channel_id,
            {
                "platform_video_id": "bulk",
                "title": "bulk",
                "description": "",
                "url": "https://www.youtube.com/watch?v=bulk",
            },
            embed_metadata=False,
        )
        high_video_id = services.upsert_video(
            channel_id,
            {
                "platform_video_id": "ultra",
                "title": "ultra",
                "description": "",
                "url": "https://www.youtube.com/watch?v=ultra",
            },
            embed_metadata=False,
        )

        bulk_job_id = services.enqueue_analysis(low_video_id, priority="bulk")
        ultra_job_id = services.enqueue_analysis(high_video_id, priority="ultra")

        claimed = worker.claim_job()

        assert claimed["id"] == ultra_job_id
        assert claimed["id"] != bulk_job_id
        assert claimed["priority"] == 0


def test_worker_reports_youtube_extraction_failure_instead_of_starting_stt(monkeypatch):
    from app import worker

    with tempfile.TemporaryDirectory() as directory:
        output_dir = Path(directory)
        youtube_failure = subprocess.CompletedProcess(
            ["yt-dlp"], 1, "", "ERROR: [youtube] video: The page needs to be reloaded."
        )
        monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: youtube_failure)
        with pytest.raises(RuntimeError, match="subtitle_download_failed: .*The page needs to be reloaded"):
            worker.download_subtitles("https://www.youtube.com/watch?v=reload", output_dir)


def test_postgres_timestamp_translation_keeps_timestamp_type():
    from app.db import _postgres_sql

    translated = _postgres_sql("UPDATE jobs SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
    assert "updated_at=CURRENT_TIMESTAMP" in translated
    assert "to_char" not in translated
