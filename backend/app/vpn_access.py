"""Authenticated reverse-proxy multi-user boundary for BAPETEN AI Evaluator.

The gateway MUST overwrite both Authorization and X-Bapeten-Vpn-User.
Uvicorn MUST remain bound to 127.0.0.1. This is not an OIDC/SSO provider.
"""
from __future__ import annotations

import hmac
import os
import re
import time
from fastapi import Request
from fastapi.responses import JSONResponse
from . import storage

_APP_URL = re.compile(r'^/api/v1/applications/([0-9a-f]{32})(?:/|$)')
_USER = re.compile(r'^[A-Za-z0-9._@-]{1,64}$')


def enabled() -> bool:
    return os.environ.get('BAPETEN_VPN_MULTIUSER', '0') == '1'


def init_vpn_db() -> None:
    with storage.db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS vpn_app_owners('
                    'app_id TEXT PRIMARY KEY, username TEXT NOT NULL, assigned_at REAL NOT NULL)')
        con.execute('CREATE INDEX IF NOT EXISTS ix_vpn_owner ON vpn_app_owners(username)')


def _check_user(username: str) -> str:
    if not _USER.fullmatch(username):
        raise ValueError('Username VPN gateway tidak valid')
    return username


def register_new(app_id: str, username: str) -> None:
    username = _check_user(username)
    if not re.fullmatch('[0-9a-f]{32}', app_id):
        raise ValueError('ID permohonan tidak valid')
    with storage.db() as con:
        con.execute('INSERT INTO vpn_app_owners(app_id,username,assigned_at) VALUES(?,?,?)',
                    (app_id, username, time.time()))


def owner_of(app_id: str) -> str | None:
    with storage.db() as con:
        result = con.execute('SELECT username FROM vpn_app_owners WHERE app_id=?',
                             (app_id,)).fetchone()
    return result['username'] if result else None


def assign_existing(app_id: str, username: str) -> None:
    username = _check_user(username)
    if not re.fullmatch('[0-9a-f]{32}', app_id) or not storage.app_exists(app_id):
        raise ValueError('Permohonan tidak ditemukan')
    with storage.db() as con:
        current = con.execute('SELECT username FROM vpn_app_owners WHERE app_id=?',
                              (app_id,)).fetchone()
        if current:
            raise ValueError('Permohonan sudah memiliki pemilik; tidak menimpa')
        con.execute('INSERT INTO vpn_app_owners(app_id,username,assigned_at) VALUES(?,?,?)',
                    (app_id, username, time.time()))


async def gateway_middleware(request: Request, call_next):
    if request.method == 'OPTIONS':
        return await call_next(request)
    path = request.url.path
    if not enabled() or not path.startswith('/api/v1/') or path == '/api/v1/health':
        return await call_next(request)
    # The proxy injects the hidden backend token; browser credentials are not forwarded.
    bearer = request.headers.get('authorization', '')
    token = os.environ.get('BAPETEN_API_TOKEN', '')
    candidate = bearer[7:].strip() if bearer.startswith('Bearer ') else ''
    if not token or not hmac.compare_digest(candidate, token):
        return JSONResponse({'detail': 'Gateway API tidak terautentikasi'}, status_code=401)
    username = request.headers.get('x-bapeten-vpn-user', '').strip()
    if not _USER.fullmatch(username):
        return JSONResponse({'detail': 'Identitas evaluator tidak tersedia'}, status_code=403)
    app_match = _APP_URL.match(path)
    if app_match and owner_of(app_match.group(1)) != username:
        return JSONResponse({'detail': 'Permohonan tidak ditemukan'}, status_code=404)
    return await call_next(request)
