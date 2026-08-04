import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "video_rag.db"))
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "mock").lower()
CHAT_PROVIDER = os.getenv("CHAT_PROVIDER", "mock").lower()
CLOVASTUDIO_API_KEY = os.getenv("CLOVASTUDIO_API_KEY")
CLOVA_MODEL = os.getenv("CLOVA_MODEL", "HCX-DASH-002")
CLOVA_SPEECH_INVOKE_URL = os.getenv("CLOVA_SPEECH_INVOKE_URL")
CLOVA_SPEECH_API_KEY = os.getenv("CLOVA_SPEECH_API_KEY")
YTDLP_BIN = os.getenv("YTDLP_BIN", "yt-dlp")
DATA_DIR = DATABASE_PATH.parent
SESSION_COOKIE_NAME = "video_rag_session"
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 30)))
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
