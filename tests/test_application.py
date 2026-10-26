import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, patch

_temp = tempfile.TemporaryDirectory(prefix="vpn-admin-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_temp.name}/test.db"
os.environ["SESSION_SECRET"] = "test-session-secret-not-a-production-credential"
os.environ["JWT_SECRET"] = "test-jwt-secret-not-a-production-credential"
os.environ["APP_ENV"] = "test"
os.environ["ALLOW_TEST_PAYMENTS"] = "false"

from fastapi.testclient import TestClient
from app.main import app
from app.config import clear_runtime_config_cache
from app.database import SessionLocal
from app.models import ClaimRecord, Order, User, VpnConfig, VpnServer
from app.services.installer import complete_install, reset_database_for_install, set_setting
from app.services.legacy_import import import_legacy_sqlite
from app.services.amnezia_wg import AMNEZIA_WG_ENDPOINTS, build_amnezia_config
from app.services.auth import decode_access_token
from app.settings import settings

CONFIG = "[Interface]\nPrivateKey = TEST_ONLY\nAddress = 10.8.0.2/24\n\n[Peer]\nPublicKey = TEST_ONLY\nEndpoint = original.example:51820\nAllowedIPs = 0.0.0.0/0\n"


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(app, follow_redirects=False))
        with SessionLocal() as db:
            complete_install(db, {
                "admin_username": "admin", "admin_password": "test-password-123",
                "settings": {"brand": "vpn-admin", "expired_config_grace_days": "1"},
                "periods": [{"code": "30", "label": "30 days", "days": 30, "price": 49}],
                "servers": [{"code": "FI-2", "name": "Finland", "api_url": "https://wg.example",
                             "username": "test", "password": "test", "subnet": "10.8.0.0/24"}],
                "products": [],
            })
        self.enterContext(patch("app.services.wg_easy.list_clients", new=AsyncMock(return_value=[])))

    def login(self, username="admin", password="test-password-123"):
        response = self.client.post("/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 303)

    def test_install_wizard_and_reinstall_lock(self):
        with SessionLocal() as db:
            reset_database_for_install(db)
            db.commit()
        clear_runtime_config_cache()
        self.assertEqual(self.client.get("/").headers["location"], "/install")
        self.assertEqual(self.client.get("/install").status_code, 200)
        response = self.client.post("/install", data={
            "admin_username": "owner", "admin_password": "long-test-password",
            "admin_password_repeat": "long-test-password", "brand": "vpn-admin",
            "period_code": "30", "period_label": "30 days", "period_days": "30", "period_price": "49",
            "server_code": "FI-2", "server_name": "Finland", "server_api_url": "https://wg.example",
            "server_host": "https://ping.example/health", "server_subnet": "10.8.0.0/24",
        })
        self.assertEqual(response.status_code, 303)
        with SessionLocal() as db:
            self.assertEqual(db.query(VpnServer).one().server_host, "https://ping.example/health")
        self.assertEqual(self.client.post("/install", data={}).status_code, 303)
        self.login("owner", "long-test-password")
        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_public_pages_and_errors(self):
        for path in ("/", "/login", "/register", "/privacy", "/terms", "/password/telegram"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
        self.assertEqual(self.client.get("/health").json(), {"ok": True})
        self.assertEqual(self.client.get("/static/favicon.svg").status_code, 200)
        error = self.client.get("/not-found")
        self.assertEqual(error.status_code, 404)
        self.assertIn("text/html", error.headers["content-type"])
        self.assertEqual(self.client.get("/not-found", headers={"Accept": "application/json"}).status_code, 404)
        self.assertEqual(self.client.get("/api/servers/ping").status_code, 401)

    def test_admin_sections_and_api_schemas(self):
        self.login()
        paths = ["/admin", "/admin/users", "/admin/orders", "/admin/configs", "/admin/servers",
                 "/admin/security", "/admin/monitoring", "/admin/settings", "/admin/api/stats", "/cabinet"]
        paths += [f"/admin/settings/{part}" for part in (
            "app", "ggsel", "payments", "telegram", "operations", "import", "legal", "periods", "products")]
        paths += ["/configs/my", "/admin-old/orders", "/admin-old/configs"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        token = self.client.post("/api/auth/token", data={"username": "admin", "password": "test-password-123"}).json()
        self.assertEqual(decode_access_token(token["access_token"])["sub"], "1")
        self.assertIsNone(decode_access_token(token["access_token"] + "tamper"))

    def test_order_callback_is_idempotent_and_renewal(self):
        self.login()
        with patch("app.services.wg_easy.get_server_capacity", new=AsyncMock(return_value={"sellable": True})):
            response = self.client.post("/orders/create", data={"server_id": "FI-2", "period_key": "30"})
        self.assertEqual(response.status_code, 303)
        with SessionLocal() as db:
            order = db.query(Order).one()
            order.provider_payment_id = "test-payment"
            order_id = order.id
            set_setting(db, "platega_enabled", "true")
            set_setting(db, "platega_merchant_id", "test-merchant")
            set_setting(db, "platega_secret", "test-secret")
            db.commit()
        clear_runtime_config_cache()
        payload = {"transactionId": "test-payment", "status": "CONFIRMED"}
        self.assertEqual(self.client.post("/payments/platega/callback", json=payload).status_code, 403)
        client = {"id": "client-1", "expiresAt": "2099-01-01T00:00:00Z"}
        with patch("app.services.wg_easy.get_server_capacity", new=AsyncMock(return_value={"sellable": True})), \
             patch("app.services.wg_easy.find_client", new=AsyncMock(side_effect=[None, client])), \
             patch("app.services.wg_easy.create_client", new=AsyncMock()) as create_client, \
             patch("app.services.wg_easy.get_client_config", new=AsyncMock(return_value=CONFIG)):
            for _ in range(2):
                result = self.client.post("/payments/platega/callback", json=payload,
                                          headers={"X-MerchantId": "test-merchant", "X-Secret": "test-secret"})
                self.assertEqual(result.status_code, 200)
            self.assertEqual(create_client.await_count, 1)
        with SessionLocal() as db:
            self.assertEqual(db.query(VpnConfig).count(), 1)
            self.assertEqual(db.get(Order, order_id).status, "paid")
            config_id = db.query(VpnConfig).one().id
        self.assertEqual(self.client.get("/configs/my").json()[0]["id"], config_id)
        self.assertEqual(self.client.post(f"/orders/renew/{config_id}", data={"period_key": "30"}).status_code, 303)
        with SessionLocal() as db:
            self.assertEqual(db.query(Order).count(), 2)

    def test_claim_variants_and_download_session(self):
        with SessionLocal() as db:
            config = VpnConfig(unique_code="test-claim", server_id="FI-2", config_name="test",
                               config_text=CONFIG, server_host="https://wg.example", is_active=True)
            db.add(config)
            db.flush()
            db.add(ClaimRecord(unique_code="test-claim", config_id=config.id, server_id="FI-2", period_key="30"))
            db.commit()
        path = "/claim/download/amnezia?unique_code=test-claim"
        self.assertEqual(self.client.get(path).status_code, 403)
        claim = self.client.get("/claim?uniquecode=test-claim")
        self.assertEqual(claim.status_code, 200)
        self.assertIn("QR-код Amnezia WG", claim.text)
        self.assertIn("103.110.64.30:51820", self.client.get(path).text)
        self.assertEqual(self.client.get("/claim/download?unique_code=test-claim").text, CONFIG)
        self.assertEqual(self.client.get("/claim/download/amnezia?unique_code=other").status_code, 403)
        for code, endpoint in AMNEZIA_WG_ENDPOINTS.items():
            self.assertIn(endpoint, build_amnezia_config(CONFIG, code).text)

    def test_user_permissions_and_ownership(self):
        self.client.post("/auth/register", data={"username": "customer", "password": "customer-password"})
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.get("/configs/my/999/download").status_code, 404)
        self.assertEqual(self.client.post("/orders/renew/999", data={"period_key": "30"}).status_code, 404)
        self.assertEqual(self.client.post("/orders/create", data={"server_id": "bad", "period_key": "30"}).status_code, 400)

    def test_disabled_payments_cannot_be_forged(self):
        self.login()
        self.assertEqual(self.client.post("/payments/platega/callback", json={"id": "anything", "status": "CONFIRMED"}).status_code, 403)
        self.assertEqual(self.client.get("/payments/mock/1").status_code, 404)
        with patch.object(settings, "app_env", "prod"), patch.object(settings, "allow_test_payments", True):
            self.assertEqual(self.client.get("/payments/mock/1").status_code, 404)

    def test_telegram_code_and_password_recovery(self):
        self.login()
        response = self.client.post("/auth/telegram/link-code")
        code = parse_qs(urlparse(response.headers["location"]).query)["telegram_code"][0]
        self.assertEqual(self.client.post("/api/telegram/link", data={"code": code, "telegram_id": "12345"}).status_code, 200)
        self.assertEqual(self.client.post("/api/telegram/link", data={"code": code, "telegram_id": "54321"}).status_code, 400)
        with patch("app.routers.auth.send_telegram_message", new=AsyncMock(return_value=(True, "sent"))):
            self.assertEqual(self.client.post("/auth/telegram/reset/request", data={"username": "admin"}).status_code, 303)
        from app.models import TelegramAuthCode
        with SessionLocal() as db:
            reset = db.query(TelegramAuthCode).filter(TelegramAuthCode.purpose == "password_reset").one()
            reset_code = reset.code
        response = self.client.post("/auth/telegram/reset/confirm", data={
            "username": "admin", "code": reset_code,
            "new_password": "new-test-password", "new_password_repeat": "new-test-password",
        })
        self.assertEqual(response.status_code, 303)
        self.login(password="new-test-password")

    def test_legacy_import_is_repeatable(self):
        path = Path(_temp.name) / "legacy.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS vpn_configs (unique_code TEXT, server_id TEXT, config_text TEXT)")
            conn.execute("DELETE FROM vpn_configs")
            conn.execute("INSERT INTO vpn_configs VALUES (?, ?, ?)", ("legacy-code", "FI-2", CONFIG))
        with SessionLocal() as db:
            self.assertEqual(import_legacy_sqlite(db, str(path))["configs_created"], 1)
            self.assertEqual(import_legacy_sqlite(db, str(path))["configs_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
