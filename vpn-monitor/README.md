# vpn-monitor

Monorepo with NestJS backend + Vue frontend for server and WG-easy monitoring.

## Run

```bash
cp .env.example .env
docker compose up --build
```

## Apps

- `apps/backend`: API, auth, metrics polling, WG proxy
- `apps/frontend`: SPA dashboards and server/client management
