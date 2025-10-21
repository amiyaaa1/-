from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .sandbox import manager
from .schemas import (
    CookieFileInfo,
    CookieListResponse,
    SandboxCreateRequest,
    SandboxInfo,
    SandboxListResponse,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Chrome 沙箱自动化平台", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    await manager.startup()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await manager.shutdown()


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/sandboxes", response_model=SandboxListResponse)
async def list_sandboxes() -> SandboxListResponse:
    sandboxes = await manager.list_sandboxes()
    return SandboxListResponse(sandboxes=[sandbox.to_dict() for sandbox in sandboxes])


@app.post("/api/sandboxes", response_model=SandboxListResponse, status_code=status.HTTP_201_CREATED)
async def create_sandboxes(request: SandboxCreateRequest) -> SandboxListResponse:
    try:
        sandboxes = await manager.create_sandboxes(
            count=request.count,
            target_url=str(request.target_url) if request.target_url else None,
            enable_google_login=request.enable_google_login,
            auto_site_login=request.auto_site_login,
            accounts_blob=request.accounts_blob,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    created = [sandbox.to_dict() for sandbox in sandboxes]
    return SandboxListResponse(sandboxes=created)


@app.delete(
    "/api/sandboxes/{sandbox_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_sandbox(sandbox_id: str) -> Response:
    try:
        await manager.remove_sandbox(sandbox_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/sandboxes/{sandbox_id}", response_model=SandboxInfo)
async def get_sandbox(sandbox_id: str) -> SandboxInfo:
    try:
        sandbox = await manager.get_sandbox(sandbox_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return sandbox.to_dict()


@app.get("/api/cookies", response_model=CookieListResponse)
async def list_cookies() -> CookieListResponse:
    files: List[CookieFileInfo] = []
    for file_path in sorted(config.COOKIE_DIR.glob("*.txt")):
        email = "unknown"
        domain = "unknown"
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            email = payload.get("email", email)
            domain = payload.get("domain", domain)
        except Exception:
            pass
        files.append(
            CookieFileInfo(
                filename=file_path.name,
                email=email,
                domain=domain,
                url=f"/api/cookies/{quote(file_path.name)}",
            )
        )
    return CookieListResponse(cookies=files)


@app.get("/api/cookies/{filename}")
async def download_cookie(filename: str) -> FileResponse:
    file_path = config.COOKIE_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Cookie 文件不存在")
    return FileResponse(file_path)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def root() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="前端资源缺失")
    return FileResponse(index_file)
