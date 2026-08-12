import importlib
import os
import tempfile

from fastapi.testclient import TestClient


def _reload_app(database_path: str):
    os.environ["DATABASE_PATH"] = database_path
    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["CHAT_PROVIDER"] = "mock"

    from app import config, db, folders, main, services, workspaces
    from app.routers import folders as folders_router

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(services)
    importlib.reload(folders)
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
