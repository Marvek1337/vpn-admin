from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_admin_user
from app.models import VpnServer
from app.services.cleanup import cleanup_expired_clients
from app.services.monitoring_service import collect_all_servers_capacity, collect_server_capacity, save_server_stat
from app.services.server_registry import audit

router = APIRouter(prefix="/admin/monitoring", tags=["Admin Monitoring"])
templates = Jinja2Templates(directory="app/templates")


def back(message: str | None = None):
    if message:
        return RedirectResponse(f"/admin/monitoring?message={message}", status_code=303)
    return RedirectResponse("/admin/monitoring", status_code=303)


@router.get("", response_class=HTMLResponse)
async def monitoring_page(request: Request, message: str = "", db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    data = await collect_all_servers_capacity(db)
    return templates.TemplateResponse("admin/monitoring.html", {
        "request": request,
        "admin": admin,
        "message": message,
        "items": data["items"],
        "totals": data["totals"],
    })


@router.get("/api", response_class=JSONResponse)
async def monitoring_api(db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    return JSONResponse(await collect_all_servers_capacity(db))


@router.post("/check-all")
async def monitoring_check_all(request: Request, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    data = await collect_all_servers_capacity(db, persist=True)
    audit(db, admin.id, "monitoring_check_all", "server", None, request.client.host if request.client else None, json.dumps(data["totals"], ensure_ascii=False))
    return back(f"Проверено серверов: {data['totals']['total_servers']}, доступно: {data['totals']['online_servers']}")


@router.post("/cleanup-expired")
async def monitoring_cleanup_expired(request: Request, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    result = await cleanup_expired_clients(db)
    audit(db, admin.id, "monitoring_cleanup_expired", "server", None, request.client.host if request.client else None, json.dumps(result, ensure_ascii=False))
    return back(f"Очистка выполнена: удалено {result['deleted']} из {result['checked']}")


@router.post("/{server_id}/check")
async def monitoring_check_server(request: Request, server_id: int, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    row = db.query(VpnServer).filter(VpnServer.id == server_id).first()
    if not row:
        raise HTTPException(404, "server not found")
    item = await collect_server_capacity(row)
    save_server_stat(db, item)
    db.commit()
    audit(db, admin.id, "monitoring_check_server", "server", row.code, request.client.host if request.client else None, json.dumps({"online": item["online"], "free": item["free"], "error": item["error"]}, ensure_ascii=False))
    return back(f"{row.name}: свободно {item['free']}" if item["online"] else f"{row.name}: {item['error']}")


@router.post("/{server_id}/cleanup")
async def monitoring_cleanup_server(request: Request, server_id: int, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    row = db.query(VpnServer).filter(VpnServer.id == server_id).first()
    if not row:
        raise HTTPException(404, "server not found")
    result = await cleanup_expired_clients(db, row)
    audit(db, admin.id, "monitoring_cleanup_server", "server", row.code, request.client.host if request.client else None, json.dumps(result, ensure_ascii=False))
    return back(f"{row.name}: удалено {result['deleted']} из {result['checked']}")
