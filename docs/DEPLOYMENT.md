# Deployment Notes — Google OAuth Gate

These notes cover the auth-specific configuration. They assume your Fly.io app
already exists and that the rest of the deployment (Dockerfile, Procfile, etc.)
is wired up.

## Google Cloud setup

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a new project if you don't have one
3. OAuth consent screen — choose "External", fill in app name, support email,
   and developer contact. You can leave it in Testing mode while you collect
   feedback (Google allows up to 100 test users without verification)
4. Credentials — Create credentials, "OAuth client ID", Application type "Web application"
5. Authorized redirect URIs — add BOTH:
   - `http://localhost:8000/auth/callback` (for local development)
   - `https://<your-fly-app>.fly.dev/auth/callback` (your production URL)
6. Save. Copy the Client ID and Client Secret.

## Environment variables

The app requires four environment variables to start. If any is missing,
`create_app()` raises `RuntimeError` at startup and Fly will mark the deploy
as failed.

| Variable | Local dev | Production |
|---|---|---|
| `GOOGLE_CLIENT_ID` | from Google Cloud Console | same |
| `GOOGLE_CLIENT_SECRET` | from Google Cloud Console | same |
| `SESSION_SECRET` | any 32+ char string | a freshly generated 32+ byte random hex |
| `APP_BASE_URL` | `http://localhost:8000` | `https://<your-fly-app>.fly.dev` |
| `COOKIE_SECURE` | `false` or unset | `true` |

Generate a fresh `SESSION_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Setting Fly secrets

From the repo root with `flyctl` installed:

```bash
flyctl secrets set \
  GOOGLE_CLIENT_ID="<paste here>" \
  GOOGLE_CLIENT_SECRET="<paste here>" \
  SESSION_SECRET="<paste 64-char hex>" \
  APP_BASE_URL="https://<your-fly-app>.fly.dev" \
  COOKIE_SECURE="true"
```

Fly will restart the app automatically once the secrets are saved.

## Local development

Create a `.env` file at the repo root (this file is gitignored — do not commit it).

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SESSION_SECRET=any-string-at-least-32-chars-long
APP_BASE_URL=http://localhost:8000
```

Load it before running locally. In PowerShell:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
  }
}
uv run python -m uvicorn app.web:create_app --factory --port 8000
```

## Verifying the deploy

After deploying:

1. `curl https://<your-fly-app>.fly.dev/api/health` should return `{"status":"ok"}`
   with no auth.
2. `curl -i https://<your-fly-app>.fly.dev/` should return 303 redirect to `/login`.
3. `curl -i https://<your-fly-app>.fly.dev/api/datasets` should return 401.
4. Visit `https://<your-fly-app>.fly.dev/login` in a browser, click "Sign in
   with Google", complete the flow, and confirm the main app loads.

## What this auth does NOT do

- No allowlist. Any Google account that completes the flow is granted access.
  If you want to restrict access to specific emails, add a check in
  `src/app/auth.py` `auth_callback` after the email is extracted.
- No rate limiting. A signed-in user can still drain your DeepSeek API budget
  by spamming `/api/chat`. Consider adding `slowapi` or a per-session counter
  if cost is a concern.
- No session persistence across `SESSION_SECRET` rotation. Rotating the secret
  invalidates every existing session.
- No CSRF protection beyond `SameSite=Lax` on the session cookie. Authlib
  generates and validates the OAuth state parameter, which is sufficient for
  the OAuth flow itself.
