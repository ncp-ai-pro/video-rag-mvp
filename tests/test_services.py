import importlib
import json
import os
import tempfile
import threading
import time

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

        with TestClient(main.app) as second_browser:
            second_workspace = second_browser.get("/auth/me").json()
            assert second_workspace["workspace_code"] != first_workspace["workspace_code"]
            connected = second_browser.post("/auth/workspace", json={"workspace_code": first_workspace["workspace_code"]})
            assert connected.status_code == 200
            assert second_browser.get("/auth/me").json()["workspace_code"] == first_workspace["workspace_code"]


def test_chat_router_keeps_post_contract_and_workspace_scope():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["DATABASE_PATH"] = os.path.join(directory, "chat.db")
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["CHAT_PROVIDER"] = "mock"
        from app import config, db, dependencies, main, services, workspaces
        from app.routers import chat

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(services)
        importlib.reload(workspaces)
        importlib.reload(dependencies)
        importlib.reload(chat)
        importlib.reload(main)

        assert any(route.path == "/chat" and "POST" in route.methods for route in main.app.routes)

        with TestClient(main.app) as owner:
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

            response = owner.post("/chat", json={"query": "자막 근거"})
            assert response.status_code == 200
            assert set(response.json()) == {"answer", "evidence"}
            assert response.json()["evidence"][0]["video_id"] == video["video_id"]

        with TestClient(main.app) as other_workspace:
            assert other_workspace.get(f"/videos/{video['video_id']}").status_code == 404
            response = other_workspace.post("/chat", json={"query": "자막 근거"})
            assert response.status_code == 200
            assert response.json()["evidence"] == []


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
