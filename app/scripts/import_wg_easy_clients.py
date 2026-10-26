"""Import WG-Easy clients. The default mode only reports proposed imports."""
import argparse
import asyncio
import json

from app.database import SessionLocal
from app.models import VpnConfig, VpnServer
from app.services import wg_easy


async def run(server_code: str, apply: bool) -> dict:
    with SessionLocal() as db:
        server = db.query(VpnServer).filter(VpnServer.code == server_code).first()
        if not server:
            raise ValueError("Server not found")
        result = {"server": server_code, "apply": apply, "created": 0, "skipped": 0}
        for client in await wg_easy.list_clients(server_code):
            name = str(client.get("name") or "").strip()
            client_id = client.get("id")
            exists = db.query(VpnConfig).filter(
                VpnConfig.unique_code == name, VpnConfig.server_id == server_code,
            ).first()
            if not name or not client_id or exists:
                result["skipped"] += 1
                continue
            if apply:
                config_text = await wg_easy.get_client_config(server_code, client_id)
                expires_at = wg_easy.parse_wg_datetime(client.get("expiresAt"))
                db.add(VpnConfig(
                    unique_code=name, config_name=name, server_id=server_code,
                    config_text=config_text, external_id=str(client_id),
                    server_host=server.api_url or server.panel_url or "",
                    expires_at=expires_at, is_active=bool(client.get("enabled", True)),
                ))
            result["created"] += 1
        if apply:
            db.commit()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", help="Server code from the admin panel")
    parser.add_argument("--apply", action="store_true", help="Write new configs to the database")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.server, args.apply)), ensure_ascii=False, indent=2))
