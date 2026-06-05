"""App-wide password gate on Railway only (APP_PASSWORD env var)."""

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


def _is_railway() -> bool:
    return bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"))


def app_password() -> str:
    return (os.environ.get("APP_PASSWORD") or "").strip()


def auth_enabled() -> bool:
    return _is_railway() and bool(app_password())


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
    <title>ACCESS — Sementic Lab PoC</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        font-family: "IBM Plex Sans", system-ui, sans-serif;
        background: #e4e2db;
        background-image:
          linear-gradient(rgba(0,0,0,0.06) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,0,0,0.06) 1px, transparent 1px);
        background-size: 24px 24px;
        color: #121110;
      }}
      .banner {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        padding: 0.45rem 1rem;
        background: repeating-linear-gradient(-45deg,#1a1917,#1a1917 8px,#e8a020 8px,#e8a020 16px);
        color: #fff;
        font: 600 0.68rem/1 "IBM Plex Mono", monospace;
        letter-spacing: 0.12em;
        text-align: center;
        text-transform: uppercase;
        border-bottom: 2px solid #1a1917;
      }}
      .card {{
        width: min(22rem, 92vw);
        margin-top: 2rem;
        border: 2px solid #1a1917;
        background: #f0eeea;
      }}
      .head {{
        padding: 0.4rem 0.75rem;
        background: #1a1917;
        color: #f0eeea;
        font: 600 0.72rem/1 "IBM Plex Mono", monospace;
        letter-spacing: 0.1em;
      }}
      .body {{
        padding: 1rem 1.1rem 1.15rem;
      }}
      h1 {{
        margin: 0 0 0.35rem;
        font: 600 1rem/1.2 "IBM Plex Mono", monospace;
        letter-spacing: 0.06em;
      }}
      p {{
        margin: 0 0 1rem;
        font-size: 0.8rem;
        color: #5a5854;
      }}
      label {{
        display: block;
        font: 600 0.68rem/1 "IBM Plex Mono", monospace;
        letter-spacing: 0.1em;
        color: #5a5854;
        margin-bottom: 0.35rem;
      }}
      input[type="password"] {{
        width: 100%;
        box-sizing: border-box;
        padding: 0.5rem 0.65rem;
        border: 1px solid #1a1917;
        background: #faf9f6;
        font: 0.85rem/1 "IBM Plex Mono", monospace;
        margin-bottom: 0.85rem;
      }}
      button {{
        width: 100%;
        padding: 0.5rem 0.75rem;
        border: 2px solid #1a6b42;
        background: #1a6b42;
        color: #f0eeea;
        font: 600 0.75rem/1 "IBM Plex Mono", monospace;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        cursor: pointer;
      }}
      button:hover {{
        filter: brightness(1.08);
      }}
      .error {{
        color: #c42b2b;
        font: 500 0.78rem/1.4 "IBM Plex Mono", monospace;
        margin: 0 0 0.75rem;
      }}
    </style>
  </head>
  <body>
    <div class="banner">PoC — Lab access gate</div>
    <form class="card" method="post" action="{LOGIN_PATH}">
      <div class="head">MOD-00 · ACCESS CONTROL</div>
      <div class="body">
        <h1>SEMENTIC LAB</h1>
        <p>Enter deployment password to continue.</p>
        {err}
        <label for="password">ACCESS KEY</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required autofocus />
        <button type="submit">▶ AUTHENTICATE</button>
      </div>
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
