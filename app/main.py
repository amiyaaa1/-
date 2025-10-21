from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .sandbox_manager import SandboxManager
from .utils import parse_accounts

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SAND_BOX_DIR = Path("sandboxes")
COOKIES_DIR = Path("cookies")

app = FastAPI(title="Chrome 沙箱管理平台")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = SandboxManager(SAND_BOX_DIR, COOKIES_DIR)


@app.on_event("startup")
async def on_startup() -> None:
    await manager.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await manager.stop()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = STATIC_DIR / "index.html"
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content)


@app.post("/api/sandboxes")
async def create_sandboxes(payload: Dict[str, Any]) -> JSONResponse:
    count = int(payload.get("count", 0))
    default_url = str(payload.get("default_url", "")).strip()
    google_login = bool(payload.get("google_login", False))
    auto_site_login = bool(payload.get("auto_site_login", True))
    account_text = str(payload.get("accounts", ""))

    if count <= 0:
        raise HTTPException(status_code=400, detail="沙箱数量必须大于 0")
    if not default_url:
        raise HTTPException(status_code=400, detail="必须提供默认打开的链接")

    accounts = parse_accounts(account_text)
    if google_login and len(accounts) < count:
        raise HTTPException(status_code=400, detail="谷歌账号数量不足以分配所有沙箱")

    sandbox_ids = await manager.create_sandboxes(
        count=count,
        default_url=default_url,
        google_login=google_login,
        auto_site_login=auto_site_login,
        accounts=accounts,
    )
    return JSONResponse({"sandboxes": sandbox_ids})


@app.get("/api/sandboxes")
async def list_sandboxes() -> JSONResponse:
    sandboxes = await manager.list_sandboxes()
    return JSONResponse({"sandboxes": sandboxes})


@app.get("/api/sandboxes/{sandbox_id}/logs")
async def get_logs(sandbox_id: str) -> JSONResponse:
    sandboxes = await manager.list_sandboxes()
    for sandbox in sandboxes:
        if sandbox["id"] == sandbox_id:
            return JSONResponse({"log": sandbox.get("log", [])})
    raise HTTPException(status_code=404, detail="未找到对应沙箱")


@app.delete("/api/sandboxes/{sandbox_id}")
async def delete_sandbox(sandbox_id: str) -> JSONResponse:
    removed = await manager.delete_sandbox(sandbox_id)
    if not removed:
        raise HTTPException(status_code=404, detail="未找到对应沙箱")
    return JSONResponse({"deleted": True})


@app.get("/api/sandboxes/{sandbox_id}/cookie")
async def download_cookie(sandbox_id: str) -> FileResponse:
    sandboxes = await manager.list_sandboxes()
    for sandbox in sandboxes:
        if sandbox["id"] == sandbox_id:
            cookie_path = sandbox.get("cookie_file")
            if cookie_path:
                full_path = COOKIES_DIR / cookie_path
                if full_path.exists():
                    return FileResponse(full_path, filename=full_path.name, media_type="text/plain")
            raise HTTPException(status_code=404, detail="尚未生成 Cookie 文件")
    raise HTTPException(status_code=404, detail="未找到对应沙箱")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
