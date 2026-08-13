import importlib
import os
import tempfile

from fastapi.testclient import TestClient


def _reload_app(database_path: str):
    os.environ["DATABASE_PATH"] = database_path
    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["CHAT_PROVIDER"] = "mock"

    from app import analysis_queue, config, db, folders, main, redis_guard, services, workspaces
    from app.routers import folders as folders_router

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(analysis_queue)
    importlib.reload(services)
    importlib.reload(folders)
    importlib.reload(redis_guard)
    importlib.reload(workspaces)
    importlib.reload(folders_router)
    importlib.reload(main)
    return db, folders, main, services


def test_folder_direct_video_url_creates_manual_video_and_analysis_job(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        _, folder_services, main, _ = _reload_app(os.path.join(directory, "folder-direct.db"))

        def fake_collect(url: str):
            return [
                {
                    "platform_video_id": "direct123",
                    "title": "LangGraph RAG 직접 추가",
                    "description": "폴더에 단일 영상 링크를 추가합니다.",
                    "url": url,
                    "thumbnail_url": None,
                    "duration_seconds": 321,
                    "uploaded_at": "20260812",
                }
            ]

        monkeypatch.setattr(folder_services, "collect_channel_metadata", fake_collect)

        with TestClient(main.app) as client:
            folder = client.post("/folders", json={"name": "LangGraph RAG", "color": "amber"}).json()

            created = client.post(
                f"/folders/{folder['id']}/videos",
                json={"url": "https://www.youtube.com/watch?v=direct123", "analyze": True},
            )

            assert created.status_code == 201
            body = created.json()
            assert body["video"]["title"] == "LangGraph RAG 직접 추가"
            assert body["video"]["analysis_status"] == "queued"
            assert body["folder_video"]["source"] == "direct"
            assert body["job"]["status"] == "queued"

            videos = client.get(f"/folders/{folder['id']}/videos").json()["items"]
            assert [video["id"] for video in videos] == [body["video"]["id"]]


def test_folder_candidate_can_be_attached_and_used_as_chat_scope():
    with tempfile.TemporaryDirectory() as directory:
        db, _, main, services = _reload_app(os.path.join(directory, "folder-candidate.db"))

        with TestClient(main.app) as client:
            folder = client.post("/folders", json={"name": "CLOVA 실습", "color": "amber"}).json()
            source = client.post(
                f"/folders/{folder['id']}/channel-sources",
                json={
                    "url": "https://www.youtube.com/@navercloud",
                    "name": "NAVER Cloud AI",
                    "auto_scan": False,
                },
            ).json()

            with db.connection() as conn:
                workspace = conn.execute("SELECT id FROM users ORDER BY id DESC LIMIT 1").fetchone()
            video_id = services.upsert_video(
                source["id"],
                {
                    "platform_video_id": "candidate123",
                    "title": "CLOVA Studio RAG 후보 영상",
                    "description": "자막 근거와 embedding을 설명합니다.",
                    "url": "https://www.youtube.com/watch?v=candidate123",
                },
            )
            services.import_transcript(
                video_id,
                [
                    {
                        "start_seconds": 12,
                        "end_seconds": 28,
                        "text": "CLOVA Studio에서는 자막 근거를 embedding으로 검색해 답변에 사용합니다.",
                    }
                ],
            )

            candidates = client.get(f"/folders/{folder['id']}/candidates").json()["items"]
            assert candidates[0]["candidate_id"] == video_id
            assert candidates[0]["status"] == "new"

            attached = client.post(f"/folders/{folder['id']}/candidates/{video_id}/analyze")
            assert attached.status_code == 202
            assert attached.json()["folder_video"]["source"] == "candidate"

            chat = client.post(
                f"/folders/{folder['id']}/chat",
                json={"query": "자막 근거를 어떻게 쓰지?", "limit": 3, "evidence_mode": "simple"},
            )
            assert chat.status_code == 200
            assert chat.json()["evidence"][0]["video_id"] == video_id

            history = client.get(f"/folders/{folder['id']}/chat/history").json()["items"]
            assert [message["role"] for message in history] == ["user", "assistant"]
            assert all(message["folder_id"] == folder["id"] for message in history)
            assert workspace["id"] >= 1


def test_folder_kakao_import_extracts_unique_youtube_links_without_metadata_fetch():
    with tempfile.TemporaryDirectory() as directory:
        db, _, main, _ = _reload_app(os.path.join(directory, "kakao-import.db"))

        kakao_export = "\n".join(
            [
                "2026. 8. 12. 오후 1:01, 나 : https://www.youtube.com/watch?v=abc123&t=90s",
                "2026. 8. 12. 오후 1:02, 나 : https://youtu.be/abc123?t=120",
                "2026. 8. 12. 오후 1:03, 나 : https://m.youtube.com/shorts/shorts456",
            ]
        ).encode("utf-8")

        with TestClient(main.app) as client:
            folder = client.post("/folders", json={"name": "나에게 보낸 링크", "color": "blue"}).json()
            response = client.post(
                f"/folders/{folder['id']}/imports/kakao",
                files={"file": ("kakao.txt", kakao_export, "text/plain")},
                data={"analyze": "false", "priority": "bulk"},
            )

            assert response.status_code == 202
            body = response.json()
            assert body["total_urls"] == 3
            assert body["unique_videos"] == 2
            assert body["duplicates"] == 1
            assert body["queued_jobs"] == 0
            assert [item["provider_video_id"] for item in body["items"]] == ["abc123", "shorts456"]

            videos = client.get(f"/folders/{folder['id']}/videos").json()["items"]
            assert len(videos) == 2
            assert {video["analysis_status"] for video in videos} == {"metadata_only"}
            snapshot = client.get("/ops/queue").json()
            assert snapshot["import_batches"] == [{"status": "completed", "count": 1}]

        with db.connection() as conn:
            assert conn.execute("SELECT COUNT(*) AS count FROM import_batches").fetchone()["count"] == 1
            assert conn.execute("SELECT COUNT(*) AS count FROM import_items").fetchone()["count"] == 2


def test_folder_kakao_import_can_enqueue_bulk_priority_jobs():
    with tempfile.TemporaryDirectory() as directory:
        db, _, main, _ = _reload_app(os.path.join(directory, "kakao-import-analyze.db"))

        with TestClient(main.app) as client:
            folder = client.post("/folders", json={"name": "대량 분석", "color": "green"}).json()
            response = client.post(
                f"/folders/{folder['id']}/imports/kakao",
                files={"file": ("kakao.txt", b"https://www.youtube.com/watch?v=bulk123", "text/plain")},
                data={"analyze": "true", "priority": "bulk"},
            )

            assert response.status_code == 202
            body = response.json()
            assert body["queued_jobs"] == 1
            assert body["items"][0]["status"] == "queued"

        with db.connection() as conn:
            job = conn.execute("SELECT kind, status, priority, idempotency_key FROM jobs").fetchone()
            assert job["kind"] == "analyze_video"
            assert job["status"] == "queued"
            assert job["priority"] == 500
            assert job["idempotency_key"].endswith(":youtube:bulk123")
            assert conn.execute("SELECT COUNT(*) AS count FROM outbox_events").fetchone()["count"] == 1
