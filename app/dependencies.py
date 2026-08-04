from fastapi import HTTPException, Request


def current_workspace(request: Request):
    """Returns the workspace established by the session middleware."""
    workspace = getattr(request.state, "workspace", None)
    if workspace is None:
        raise HTTPException(status_code=401, detail="workspace session is not initialized")
    return workspace
