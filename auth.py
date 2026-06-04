"""Optional app-wide password gate (APP_PASSWORD env var)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE_NAME = "sementic_auth"
LOGIN_PATH = "/login"
PUBLIC_PREFIXES = ("/login", "/api/health")


def app_password() -> str:
    return (os.environ.get("APP_PASSWORD") or "").strip()


def auth_enabled() -> bool:
    return bool(app_password())


def _session_token() -> str:
    pwd = app_password()
    return hmac.new(pwd.encode("utf-8"), b"sementic-session", hashlib.sha256).hexdigest()


def is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True
    cookie = request.cookies.get(COOKIE_NAME, "")
    expected = _session_token()
    return bool(cookie) and secrets.compare_digest(cookie, expected)


def _is_public_path(path: str) -> bool:
    return path == LOGIN_PATH or any(
        path.startswith(prefix) for prefix in PUBLIC_PREFIXES if prefix != LOGIN_PATH
    )


class AppPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not auth_enabled():
            return await call_next(request)

        path = request.url.path
        if _is_public_path(path):
            return await call_next(request)

        if is_authenticated(request):
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        return RedirectResponse(url=LOGIN_PATH, status_code=302)


def login_page_html(*, error: str | None = None) -> str:
    err = (
        f'<p class="error">{error}</p>'
        if error
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sign in — Sementic</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,600&family=Sora:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        font-family: "Sora", system-ui, sans-serif;
        background: #f3f2ef;
        color: #1a1917;
      }}
      .card {{
        width: min(22rem, 92vw);
        padding: 1.5rem 1.35rem;
        background: #fffefb;
        border: 1px solid #ddd9d0;
        box-shadow: 0 8px 24px rgba(26, 25, 23, 0.06);
      }}
      h1 {{
        margin: 0 0 0.35rem;
        font-family: "Newsreader", Georgia, serif;
        font-size: 1.35rem;
        font-weight: 600;
      }}
      p {{
        margin: 0 0 1rem;
        font-size: 0.86rem;
        color: #64615a;
      }}
      label {{
        display: block;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #64615a;
        margin-bottom: 0.35rem;
      }}
      input[type="password"] {{
        width: 100%;
        box-sizing: border-box;
        padding: 0.55rem 0.65rem;
        border: 1px solid #ddd9d0;
        font: inherit;
        margin-bottom: 0.85rem;
      }}
      button {{
        width: 100%;
        padding: 0.55rem 0.75rem;
        border: none;
        background: #2a7d72;
        color: #fff;
        font: 600 0.9rem/1 "Sora", system-ui, sans-serif;
        cursor: pointer;
      }}
      button:hover {{
        background: #1f6359;
      }}
      .error {{
        color: #b44040;
        font-size: 0.84rem;
        margin: 0 0 0.75rem;
      }}
    </style>
  </head>
  <body>
    <form class="card" method="post" action="{LOGIN_PATH}">
      <h1>Sementic Analysis Tool</h1>
      <p>Enter the app password to continue.</p>
      {err}
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required autofocus />
      <button type="submit">Sign in</button>
    </form>
  </body>
</html>"""


def register_auth_routes(app) -> None:
    @app.get(LOGIN_PATH, response_class=HTMLResponse, response_model=None)
    async def login_page(request: Request):
        if is_authenticated(request):
            return RedirectResponse(url="/", status_code=302)
        return HTMLResponse(login_page_html())

    @app.post(LOGIN_PATH, response_model=None)
    async def login_submit(password: str = Form(...)):
        pwd = app_password()
        if secrets.compare_digest(password.strip(), pwd):
            response = RedirectResponse(url="/", status_code=302)
            response.set_cookie(
                key=COOKIE_NAME,
                value=_session_token(),
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 14,
                path="/",
            )
            return response
        response = HTMLResponse(login_page_html(error="Incorrect password."), status_code=401)
        return response

    @app.post("/logout", response_model=None)
    async def logout():
        response = RedirectResponse(url=LOGIN_PATH, status_code=302)
        response.delete_cookie(COOKIE_NAME, path="/")
        return response
