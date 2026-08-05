"""Chat Server entrypoint: uvicorn app.chat_main:app."""

from .routers.chat import router as chat_router
from .db import is_postgres
from .web import create_web_app


app = create_web_app(title="Video RAG Chat Server", version="0.2.0")


@app.get("/health")
def health():
    return {"status": "ok", "role": "chat", "mode": "postgresql" if is_postgres() else "sqlite"}


app.include_router(chat_router)
