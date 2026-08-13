import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import config
from .db import connection
from .services import (
    ANALYSIS_MESSAGES,
    enqueue,
    enqueue_analysis,
    object_storage_is_configured,
    upload_artifact_bytes,
    upsert_video,
)
from .video_identity import VideoIdentity, extract_youtube_url_mentions, normalize_youtube_url


def _iso(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if value and "T" not in str(value):
        return str(value).replace(" ", "T") + "Z"
    return value


def _folder_item(row: Dict) -> Dict:
    item = dict(row)
    for key in ("created_at", "updated_at"):
        item[key] = _iso(item.get(key))
    return item


def required_folder(folder_id: int, user_id: int) -> Dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM folders WHERE id=? AND user_id=?", (folder_id, user_id)).fetchone()
    if not row:
        raise LookupError("folder not found")
    return _folder_item(row)


def video_belongs_to_folder(user_id: int, folder_id: int, video_id: int) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT videos.id
            FROM folder_videos
            JOIN folders ON folders.id=folder_videos.folder_id
            JOIN videos ON videos.id=folder_videos.video_id
            JOIN channels ON channels.id=videos.channel_id
            WHERE folders.user_id=? AND folders.id=? AND videos.id=? AND channels.user_id=?
            """,
            (user_id, folder_id, video_id, user_id),
        ).fetchone()
    return row is not None


def list_folders(user_id: int) -> List[Dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT folders.*,
                   COUNT(folder_videos.video_id) AS video_count,
                   SUM(CASE WHEN videos.analysis_status IN ('ready', 'succeeded') THEN 1 ELSE 0 END) AS ready_count,
                   SUM(CASE WHEN videos.analysis_status='running' THEN 1 ELSE 0 END) AS running_count,
                   (
                       SELECT COUNT(*)
                       FROM videos AS candidate_videos
                       JOIN channels AS candidate_channels ON candidate_channels.id=candidate_videos.channel_id
                       WHERE candidate_channels.folder_id=folders.id
                         AND NOT EXISTS (
                             SELECT 1 FROM folder_videos AS fv
                             WHERE fv.folder_id=folders.id AND fv.video_id=candidate_videos.id
                         )
                   ) AS candidate_count
            FROM folders
            LEFT JOIN folder_videos ON folder_videos.folder_id=folders.id
            LEFT JOIN videos ON videos.id=folder_videos.video_id
            WHERE folders.user_id=?
            GROUP BY folders.id
            ORDER BY COALESCE(folders.updated_at, folders.created_at) DESC, folders.id DESC
            """,
            (user_id,),
        ).fetchall()
    return [_folder_item(row) for row in rows]


def create_folder(user_id: int, payload: Dict) -> Dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO folders(user_id, name, description, color, updated_at)
            VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            RETURNING *
            """,
            (user_id, payload["name"], payload.get("description") or "", payload.get("color")),
        ).fetchone()
    return _folder_item(row)


def update_folder(user_id: int, folder_id: int, payload: Dict) -> Dict:
    required_folder(folder_id, user_id)
    updates = []
    params = []
    for key in ("name", "description", "color"):
        if key in payload and payload[key] is not None:
            updates.append(f"{key}=?")
            params.append(payload[key])
    if not updates:
        return required_folder(folder_id, user_id)
    updates.append("updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
    params.extend([folder_id, user_id])
    with connection() as conn:
        row = conn.execute(
            f"UPDATE folders SET {', '.join(updates)} WHERE id=? AND user_id=? RETURNING *",
            tuple(params),
        ).fetchone()
    return _folder_item(row)


def delete_folder(user_id: int, folder_id: int) -> None:
    required_folder(folder_id, user_id)
    with connection() as conn:
        conn.execute("DELETE FROM folders WHERE id=? AND user_id=?", (folder_id, user_id))


def _ensure_manual_channel(user_id: int) -> int:
    manual_url = f"internal://workspace/{user_id}/manual-videos"
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO channels(user_id, url, name)
            VALUES (?, ?, '직접 추가 영상')
            ON CONFLICT(user_id, url) DO UPDATE SET name=channels.name
            RETURNING id
            """,
            (user_id, manual_url),
        ).fetchone()
    return row["id"]


def _attach_folder_video(folder_id: int, video_id: int, source: str) -> Dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO folder_videos(folder_id, video_id, source)
            VALUES (?, ?, ?)
            ON CONFLICT(folder_id, video_id) DO UPDATE SET source=excluded.source
            RETURNING *
            """,
            (folder_id, video_id, source),
        ).fetchone()
        conn.execute(
            "UPDATE folders SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id=?",
            (folder_id,),
        )
    item = dict(row)
    item["added_at"] = _iso(item.get("added_at"))
    return item


def _enqueue_if_needed(video: Dict, *, analyze: bool) -> Optional[Dict]:
    if not analyze:
        return None
    if video["analysis_status"] in ("queued", "running", "ready", "succeeded"):
        return None
    return {"job_id": enqueue_analysis(video["id"]), "status": "queued"}


def _placeholder_video(identity: VideoIdentity) -> Dict:
    return {
        "platform_video_id": identity.provider_video_id,
        "title": f"YouTube {identity.provider_video_id}",
        "description": "",
        "url": identity.canonical_url,
        "thumbnail_url": None,
        "duration_seconds": None,
        "uploaded_at": None,
    }


def _record_video_analysis_identity(identity: VideoIdentity, video_id: int, analysis_status: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO video_analysis_index(
                provider, provider_video_id, canonical_url, representative_video_id,
                analysis_status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ON CONFLICT(provider, provider_video_id) DO UPDATE SET
                canonical_url=excluded.canonical_url,
                representative_video_id=COALESCE(video_analysis_index.representative_video_id, excluded.representative_video_id),
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                identity.provider,
                identity.provider_video_id,
                identity.canonical_url,
                video_id,
                analysis_status,
            ),
        )


def _find_manual_video(channel_id: int, provider_video_id: str) -> Optional[int]:
    with connection() as conn:
        row = conn.execute(
            "SELECT id FROM videos WHERE channel_id=? AND platform_video_id=?",
            (channel_id, provider_video_id),
        ).fetchone()
    return int(row["id"]) if row else None


def _ensure_placeholder_video(channel_id: int, identity: VideoIdentity) -> int:
    existing_id = _find_manual_video(channel_id, identity.provider_video_id)
    if existing_id:
        return existing_id
    return upsert_video(channel_id, _placeholder_video(identity), embed_metadata=False)


def import_kakao_links_to_folder(
    user_id: int,
    folder_id: int,
    *,
    filename: str,
    content: bytes,
    analyze: bool,
    priority: str = "bulk",
) -> Dict:
    """Imports YouTube links from a KakaoTalk export without metadata network calls."""
    required_folder(folder_id, user_id)
    text = content.decode("utf-8-sig", errors="replace")
    mentions = extract_youtube_url_mentions(text)
    unique: List[VideoIdentity] = []
    seen: set[str] = set()
    for identity in mentions:
        if identity.provider_video_id in seen:
            continue
        unique.append(identity)
        seen.add(identity.provider_video_id)

    file_sha256 = hashlib.sha256(content).hexdigest()
    artifact_key = None
    if object_storage_is_configured():
        object_key = f"{config.OBJECT_STORAGE_IMPORT_PREFIX}/folders/{folder_id}/{file_sha256}.txt"
        artifact_key = upload_artifact_bytes(content, object_key, "text/plain; charset=utf-8")

    with connection() as conn:
        batch = conn.execute(
            """
            INSERT INTO import_batches(
                user_id, folder_id, filename, file_sha256, artifact_object_key,
                total_urls, unique_videos, duplicates
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                user_id,
                folder_id,
                filename,
                file_sha256,
                artifact_key,
                len(mentions),
                len(unique),
                max(0, len(mentions) - len(unique)),
            ),
        ).fetchone()
        batch_id = batch["id"]

    channel_id = _ensure_manual_channel(user_id)
    queued_jobs = 0
    items = []
    for identity in unique:
        video_id = _ensure_placeholder_video(channel_id, identity)
        _attach_folder_video(folder_id, video_id, "kakao_import")
        video = get_workspace_video(user_id, video_id)
        _record_video_analysis_identity(identity, video_id, video["analysis_status"])
        job = None
        item_status = "attached"
        if analyze and video["analysis_status"] not in ("queued", "running", "ready", "succeeded"):
            idempotency_key = f"analyze:{user_id}:{identity.provider}:{identity.provider_video_id}"
            job_id = enqueue_analysis(video_id, priority=priority, idempotency_key=idempotency_key)
            job = {"job_id": job_id, "status": "queued"}
            queued_jobs += 1
            item_status = "queued"
        elif video["analysis_status"] in ("queued", "running", "ready", "succeeded"):
            item_status = video["analysis_status"]

        with connection() as conn:
            conn.execute(
                """
                INSERT INTO import_items(
                    batch_id, folder_id, video_id, job_id, provider, provider_video_id,
                    source_url, canonical_url, start_seconds_hint, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    folder_id,
                    video_id,
                    job["job_id"] if job else None,
                    identity.provider,
                    identity.provider_video_id,
                    identity.canonical_url,
                    identity.canonical_url,
                    identity.start_seconds_hint,
                    item_status,
                ),
            )
        items.append(
            {
                "video_id": video_id,
                "provider": identity.provider,
                "provider_video_id": identity.provider_video_id,
                "canonical_url": identity.canonical_url,
                "start_seconds_hint": identity.start_seconds_hint,
                "status": item_status,
                "job": job,
            }
        )

    with connection() as conn:
        conn.execute(
            """
            UPDATE import_batches
            SET queued_jobs=?
            WHERE id=?
            """,
            (queued_jobs, batch_id),
        )
    return {
        "batch_id": batch_id,
        "folder_id": folder_id,
        "filename": filename,
        "artifact_object_key": artifact_key,
        "total_urls": len(mentions),
        "unique_videos": len(unique),
        "duplicates": max(0, len(mentions) - len(unique)),
        "queued_jobs": queued_jobs,
        "items": items,
    }


def add_video_url_to_folder(user_id: int, folder_id: int, url: str, *, analyze: bool, title: Optional[str] = None) -> Dict:
    required_folder(folder_id, user_id)
    identity = normalize_youtube_url(url)
    if not identity:
        raise RuntimeError("unsupported_video_url: only YouTube video URLs are supported")
    channel_id = _ensure_manual_channel(user_id)
    existing_id = _find_manual_video(channel_id, identity.provider_video_id)
    video_id = existing_id or upsert_video(channel_id, _placeholder_video(identity), embed_metadata=False)
    folder_video = _attach_folder_video(folder_id, video_id, "direct")
    video = get_workspace_video(user_id, video_id)
    _record_video_analysis_identity(identity, video_id, video["analysis_status"])
    job = None
    if existing_id and video["analysis_status"] not in ("metadata_pending",):
        job = _enqueue_if_needed(video, analyze=analyze)
    elif not existing_id or video["analysis_status"] == "metadata_pending":
        priority = "manual"
        idempotency_key = f"ingest:{user_id}:{identity.provider}:{identity.provider_video_id}"
        analysis_idempotency_key = f"analyze:{user_id}:{identity.provider}:{identity.provider_video_id}"
        job_id = enqueue(
            "ingest_video",
            video_id,
            priority=priority,
            idempotency_key=idempotency_key,
            payload={
                "analyze": analyze,
                "analysis_priority": priority,
                "analysis_idempotency_key": analysis_idempotency_key,
                "title_override": title,
            },
        )
        with connection() as conn:
            conn.execute(
                """
                UPDATE videos
                SET title=COALESCE(NULLIF(CAST(? AS TEXT), ''), title),
                    analysis_status='metadata_pending',
                    analysis_stage='metadata_pending',
                    analysis_message=?,
                    analysis_error=NULL,
                    analysis_updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id=?
                """,
                (title, ANALYSIS_MESSAGES["metadata_pending"], video_id),
            )
            conn.execute(
                """
                UPDATE video_analysis_index
                SET analysis_status='metadata_pending', last_job_id=?, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE representative_video_id=?
                """,
                (job_id, video_id),
            )
        job = {"job_id": job_id, "kind": "ingest_video", "status": "queued"}
    if job:
        video = get_workspace_video(user_id, video_id)
    return {"video": video, "folder_video": folder_video, "job": job}


def attach_existing_video_to_folder(
    user_id: int, folder_id: int, video_id: int, *, source: str, analyze: bool
) -> Dict:
    required_folder(folder_id, user_id)
    video = get_workspace_video(user_id, video_id)
    folder_video = _attach_folder_video(folder_id, video_id, source)
    job = _enqueue_if_needed(video, analyze=analyze)
    if job:
        video = get_workspace_video(user_id, video_id)
    return {"video": video, "folder_video": folder_video, "job": job}


def get_workspace_video(user_id: int, video_id: int) -> Dict:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT videos.*, channels.name AS source_label, channels.url AS source_url
            FROM videos
            JOIN channels ON channels.id=videos.channel_id
            WHERE videos.id=? AND channels.user_id=?
            """,
            (video_id, user_id),
        ).fetchone()
    if not row:
        raise LookupError("video not found")
    return _video_item(row)


def _video_item(row: Dict) -> Dict:
    item = dict(row)
    for key in ("created_at", "added_at", "analyzed_at", "analysis_updated_at", "uploaded_at"):
        item[key] = _iso(item.get(key))
    return item


def list_folder_videos(
    user_id: int,
    folder_id: int,
    *,
    status_filter: str = "all",
    query: Optional[str] = None,
    limit: int = 30,
) -> Dict:
    required_folder(folder_id, user_id)
    clauses = ["folders.user_id=?", "folders.id=?"]
    params: List = [user_id, folder_id]
    if status_filter != "all":
        clauses.append("videos.analysis_status=?")
        params.append(status_filter)
    if query:
        clauses.append("(videos.title LIKE ? OR videos.description LIKE ? OR channels.name LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])
    params.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT videos.id, videos.platform_video_id, videos.title, videos.description, videos.url,
                   videos.thumbnail_url, videos.duration_seconds, videos.uploaded_at,
                   videos.analysis_status, videos.analysis_stage, videos.analysis_message,
                   videos.analysis_error, videos.analysis_updated_at, videos.analyzed_at,
                   folder_videos.folder_id, folder_videos.source, folder_videos.position,
                   folder_videos.added_at, channels.name AS source_label,
                   (
                       SELECT COUNT(*) FROM transcript_chunks WHERE transcript_chunks.video_id=videos.id
                   ) AS evidence_count
            FROM folder_videos
            JOIN folders ON folders.id=folder_videos.folder_id
            JOIN videos ON videos.id=folder_videos.video_id
            JOIN channels ON channels.id=videos.channel_id
            WHERE {' AND '.join(clauses)}
            ORDER BY folder_videos.position IS NULL, folder_videos.position ASC, folder_videos.added_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return {"items": [_video_item(row) for row in rows], "next_cursor": None}


def remove_folder_video(user_id: int, folder_id: int, video_id: int) -> None:
    required_folder(folder_id, user_id)
    with connection() as conn:
        conn.execute(
            """
            DELETE FROM folder_videos
            WHERE folder_id=? AND video_id IN (
                SELECT videos.id
                FROM videos JOIN channels ON channels.id=videos.channel_id
                WHERE videos.id=? AND channels.user_id=?
            )
            """,
            (folder_id, video_id, user_id),
        )


def create_channel_source(user_id: int, folder_id: int, url: str, name: Optional[str]) -> Dict:
    required_folder(folder_id, user_id)
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO channels(user_id, folder_id, url, name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, url) DO UPDATE SET folder_id=excluded.folder_id, name=COALESCE(excluded.name, channels.name)
            RETURNING *
            """,
            (user_id, folder_id, url, name),
        ).fetchone()
    return _folder_item(row)


def list_channel_sources(user_id: int, folder_id: int) -> List[Dict]:
    required_folder(folder_id, user_id)
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT channels.*,
                   (
                       SELECT COUNT(*)
                       FROM videos
                       WHERE videos.channel_id=channels.id
                         AND NOT EXISTS (
                             SELECT 1 FROM folder_videos
                             WHERE folder_videos.folder_id=? AND folder_videos.video_id=videos.id
                         )
                   ) AS candidate_count
            FROM channels
            WHERE channels.user_id=? AND channels.folder_id=?
            ORDER BY channels.id DESC
            """,
            (folder_id, user_id, folder_id),
        ).fetchall()
    return [_folder_item(row) for row in rows]


def channel_source_belongs_to_folder(user_id: int, folder_id: int, source_id: int) -> bool:
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM channels WHERE id=? AND user_id=? AND folder_id=?",
            (source_id, user_id, folder_id),
        ).fetchone()
    return row is not None


def list_folder_candidates(
    user_id: int,
    folder_id: int,
    *,
    status_filter: str = "new",
    query: Optional[str] = None,
    limit: int = 30,
) -> Dict:
    required_folder(folder_id, user_id)
    clauses = ["channels.user_id=?", "channels.folder_id=?"]
    params: List = [user_id, folder_id]
    if status_filter == "new":
        clauses.append(
            """
            NOT EXISTS (
                SELECT 1 FROM folder_videos
                WHERE folder_videos.folder_id=? AND folder_videos.video_id=videos.id
            )
            """
        )
        params.append(folder_id)
    elif status_filter == "added":
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM folder_videos
                WHERE folder_videos.folder_id=? AND folder_videos.video_id=videos.id
            )
            """
        )
        params.append(folder_id)
    if query:
        clauses.append("(videos.title LIKE ? OR videos.description LIKE ? OR channels.name LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])
    params.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT videos.id, videos.platform_video_id, videos.title, videos.description, videos.url,
                   videos.thumbnail_url, videos.duration_seconds, videos.uploaded_at,
                   videos.analysis_status, channels.name AS source_label,
                   CASE
                       WHEN EXISTS (
                           SELECT 1 FROM folder_videos
                           WHERE folder_videos.folder_id=? AND folder_videos.video_id=videos.id
                       ) THEN 'added'
                       ELSE 'new'
                   END AS status
            FROM videos
            JOIN channels ON channels.id=videos.channel_id
            WHERE {' AND '.join(clauses)}
            ORDER BY videos.uploaded_at DESC, videos.id DESC
            LIMIT ?
            """,
            (folder_id, *params),
        ).fetchall()
    items = []
    for row in rows:
        item = _video_item(row)
        item["candidate_id"] = item["id"]
        item["score"] = None
        item["basis"] = "폴더에 연결된 채널 수집 메타데이터"
        items.append(item)
    return {"items": items, "next_cursor": None}


def analyze_candidate(user_id: int, folder_id: int, candidate_id: int, *, analyze: bool = True) -> Dict:
    candidate = get_workspace_video(user_id, candidate_id)
    with connection() as conn:
        source = conn.execute(
            """
            SELECT channels.id
            FROM videos JOIN channels ON channels.id=videos.channel_id
            WHERE videos.id=? AND channels.user_id=? AND channels.folder_id=?
            """,
            (candidate_id, user_id, folder_id),
        ).fetchone()
    if not source:
        raise LookupError("candidate not found")
    result = attach_existing_video_to_folder(user_id, folder_id, candidate_id, source="candidate", analyze=analyze)
    return {
        "candidate": {"id": candidate_id, "status": "queued" if result["job"] else "added"},
        **result,
    }
