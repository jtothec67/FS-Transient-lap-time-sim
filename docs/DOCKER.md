# Docker Workbench Runbook

This runs the FastAPI workbench and static interface in a container.

The compose file defaults to a localhost-only auth bypass:

```text
LOCAL_AUTH_BYPASS_EMAIL=local-dev@example.com
```

That lets you test the interface without configuring Google OAuth. For a real OAuth run, unset `LOCAL_AUTH_BYPASS_EMAIL` and provide `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, and `APP_BASE_URL`.

## Build and run

```bash
docker compose up --build
```

Open:

```text
http://localhost:3000
```

If port `3000` is already in use, choose another host port:

```bash
$env:HOST_PORT = "3011"
$env:APP_BASE_URL = "http://localhost:3011"
docker compose up --build
```

Then open:

```text
http://localhost:3011
```

Health check:

```bash
curl http://localhost:3000/api/health
```

## DeepSeek chat

For chat in Docker, pass the API key as an environment variable:

```bash
$env:DEEPSEEK_API_KEY = "sk-..."
docker compose up --build
```

The local non-Docker app still supports `config/deepseek_key`.

## Useful commands

Rebuild from scratch:

```bash
docker compose build --no-cache
```

Stop the app:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f lgr-sim-workbench
```
