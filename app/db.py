import sqlite3
from contextlib import contextmanager

from .config import DATABASE_PATH


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scanned_at TEXT,
    UNIQUE(user_id, url)
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    platform_video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    thumbnail_url TEXT,
    duration_seconds INTEGER,
    uploaded_at TEXT,
    metadata_embedding TEXT,
    analysis_status TEXT NOT NULL DEFAULT 'metadata_only',
    analysis_stage TEXT NOT NULL DEFAULT 'metadata_only',
    analysis_message TEXT,
    analysis_error TEXT,
    analysis_updated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    analyzed_at TEXT,
    UNIQUE(channel_id, platform_video_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('scan_channel', 'analyze_video')),
    resource_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued', 'running', 'succeeded', 'failed')),
    progress_stage TEXT NOT NULL DEFAULT 'queued',
    progress_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS transcript_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, id);
CREATE INDEX IF NOT EXISTS idx_channels_user ON channels(user_id, id);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_chunks_video ON transcript_chunks(video_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
"""


@contextmanager
def connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize():
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(channels)")}
        channel_schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='channels'"
        ).fetchone()
        workspace_unique = channel_schema and "UNIQUE(user_id, url)" in channel_schema["sql"]
        channel_count = conn.execute("SELECT COUNT(*) AS count FROM channels").fetchone()["count"] if columns else 0
        video_count = conn.execute("SELECT COUNT(*) AS count FROM videos").fetchone()["count"] if columns else 0
        if columns and not workspace_unique and channel_count == 0 and video_count == 0:
            conn.execute("DROP TABLE channels")
            columns = set()
        if columns and "user_id" not in columns:
            conn.execute("ALTER TABLE channels ADD COLUMN user_id INTEGER REFERENCES users(id)")
        conn.executescript(SCHEMA)
        _add_column_if_missing(conn, "videos", "analysis_stage", "TEXT")
        _add_column_if_missing(conn, "videos", "analysis_message", "TEXT")
        _add_column_if_missing(conn, "videos", "analysis_updated_at", "TEXT")
        _add_column_if_missing(conn, "jobs", "progress_stage", "TEXT")
        _add_column_if_missing(conn, "jobs", "progress_message", "TEXT")
        _add_column_if_missing(conn, "jobs", "updated_at", "TEXT")
        conn.execute("UPDATE videos SET analysis_status='succeeded' WHERE analysis_status='ready'")
        conn.execute(
            """
            UPDATE videos
            SET analysis_stage=COALESCE(
                    analysis_stage,
                    CASE analysis_status
                        WHEN 'succeeded' THEN 'completed'
                        WHEN 'failed' THEN 'failed'
                        WHEN 'running' THEN 'downloading_caption'
                        WHEN 'queued' THEN 'queued'
                        ELSE 'metadata_only'
                    END
                ),
                analysis_updated_at=COALESCE(analysis_updated_at, analyzed_at, created_at)
            """
        )
        conn.execute(
            """
            UPDATE jobs
            SET progress_stage=COALESCE(
                    progress_stage,
                    CASE status
                        WHEN 'succeeded' THEN 'completed'
                        WHEN 'failed' THEN 'failed'
                        WHEN 'running' THEN 'downloading_caption'
                        ELSE 'queued'
                    END
                ),
                updated_at=COALESCE(updated_at, finished_at, started_at, created_at)
            """
        )


def _add_column_if_missing(conn, table: str, column: str, definition: str):
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
