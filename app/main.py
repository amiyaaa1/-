from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .sandbox_manager import SandboxManager
from .schemas import SandboxLaunchRequest, SandboxListResponse, SandboxStartResponse

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR.parent / "runtime"
manager = SandboxManager(WORK_DIR)

app = FastAPI(title="Chrome 沙箱自动化平台")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _make_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/sandboxes", response_model=SandboxListResponse)
async def list_sandboxes(request: Request) -> SandboxListResponse:
    base_url = _make_base_url(request)
    statuses = await manager.list_status()
    items = [status.to_response(base_url) for status in statuses]
    return SandboxListResponse(items=items)


@app.post("/api/sandboxes/start", response_model=SandboxStartResponse)
async def start_sandboxes(request: Request, payload: SandboxLaunchRequest) -> SandboxStartResponse:
    try:
        statuses = await manager.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    base_url = _make_base_url(request)
    items = [status.to_response(base_url) for status in statuses]
    return SandboxStartResponse(items=items)


@app.get("/api/sandboxes/{sandbox_id}/cookie")
async def download_cookie(sandbox_id: str) -> FileResponse:
    status = await manager.get_status(sandbox_id)
    if not status or not status.cookie_file:
        raise HTTPException(status_code=404, detail="Cookie 文件尚未生成")
    return FileResponse(path=status.cookie_file, filename=status.cookie_file.name)
