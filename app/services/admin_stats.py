from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Order, ServerStat, User, VpnConfig, VpnServer


def _day_key(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m")


def build_admin_dashboard_stats(db: Session) -> dict:
    now = datetime.utcnow()
    week_until = now + timedelta(days=7)
    since = now - timedelta(days=13)

    total_users = db.query(User).count()
    total_orders = db.query(Order).count()
    paid_orders = db.query(Order).filter(Order.status == "paid").count()
    total_configs = db.query(VpnConfig).count()
    active_configs = db.query(VpnConfig).filter(VpnConfig.is_active == True).count()  # noqa: E712
    expiring_configs = db.query(VpnConfig).filter(
        VpnConfig.is_active == True,  # noqa: E712
        VpnConfig.expires_at.isnot(None),
        VpnConfig.expires_at <= week_until,
    ).count()
    total_servers = db.query(VpnServer).count()
    active_servers = db.query(VpnServer).filter(VpnServer.is_active == True).count()  # noqa: E712
    revenue = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(Order.status == "paid").scalar() or 0

    recent_orders = db.query(Order).filter(Order.created_at >= since).order_by(Order.created_at.asc()).all()
    day_counts = defaultdict(int)
    day_revenue = defaultdict(float)
    for item in recent_orders:
        key = _day_key(item.created_at)
        if not key:
            continue
        day_counts[key] += 1
        if item.status == "paid":
            day_revenue[key] += float(item.amount or 0)

    timeline = []
    for offset in range(13, -1, -1):
        day = (date.today() - timedelta(days=offset)).strftime("%d.%m")
        timeline.append({
            "day": day,
            "orders": day_counts.get(day, 0),
            "revenue": int(day_revenue.get(day, 0)),
        })
    max_orders = max([item["orders"] for item in timeline] or [1]) or 1
    max_revenue = max([item["revenue"] for item in timeline] or [1]) or 1
    for item in timeline:
        item["orders_pct"] = int((item["orders"] / max_orders) * 100) if max_orders else 0
        item["revenue_pct"] = int((item["revenue"] / max_revenue) * 100) if max_revenue else 0

    status_counts = Counter(row[0] for row in db.query(Order.status).all())
    total_status = sum(status_counts.values()) or 1
    statuses = [
        {"label": key, "count": value, "pct": int((value / total_status) * 100)}
        for key, value in status_counts.most_common()
    ]

    latest_server_stats = {}
    for stat in db.query(ServerStat).order_by(ServerStat.id.desc()).limit(500).all():
        latest_server_stats.setdefault(stat.server_code, stat)
    online_servers = sum(1 for item in latest_server_stats.values() if item.online)
    total_free_ips = sum((item.free_ips or 0) for item in latest_server_stats.values())

    return {
        "cards": {
            "users": total_users,
            "orders": total_orders,
            "paid_orders": paid_orders,
            "revenue": int(revenue),
            "configs": total_configs,
            "active_configs": active_configs,
            "expiring_configs": expiring_configs,
            "servers": total_servers,
            "active_servers": active_servers,
            "online_servers": online_servers,
            "free_ips": total_free_ips,
        },
        "timeline": timeline,
        "statuses": statuses,
        "latest_server_stats": latest_server_stats,
    }
