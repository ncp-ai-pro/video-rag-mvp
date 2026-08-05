"""Shared HTTP setup for the API and separately deployed Chat Server."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    CORS_ALLOW_ORIGINS,
    SESSION_COOKIE_DOMAIN,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
)
from .db import initialize
from .workspaces import create_guest_workspace, create_session, session_workspace


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    yield


def create_web_app(*, title: str, version: str) -> FastAPI:
    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ALLOW_ORIGINS),
        allow_origin_regex=None if CORS_ALLOW_ORIGINS else ".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def workspace_session(request: Request, call_next):
        if request.url.path in {"/health", "/runtime-config.js"}:
            return await call_next(request)

        workspace = session_workspace(request.cookies.get(SESSION_COOKIE_NAME))
        if workspace is None:
            workspace = create_guest_workspace()
            request.state.new_session_token = create_session(workspace["id"])
        request.state.workspace = workspace
        response = await call_next(request)
        if getattr(request.state, "new_session_token", None):
            set_session_cookie(response, request.state.new_session_token)
        return response

    return app


def set_session_cookie(response: Response, token: str) -> None:
    options = {
        "key": SESSION_COOKIE_NAME,
        "value": token,
        "max_age": SESSION_MAX_AGE_SECONDS,
        "httponly": True,
        "secure": SESSION_COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    if SESSION_COOKIE_DOMAIN:
        options["domain"] = SESSION_COOKIE_DOMAIN
    response.set_cookie(**options)
