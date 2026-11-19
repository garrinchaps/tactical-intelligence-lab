"""
Rodada 21 — CONTAS de quem entra pelo link (cada um com a sua senha, ou pelo Google) e painel do dono.

* Banco próprio e pequeno: data/contas.db (fora do Git, como todo *.db). Senha guardada só como hash scrypt (biblioteca
  padrão, com sal por conta) — nunca o texto. O app nunca imprime senha, sal, hash ou o segredo dos cookies.
* "Lembrar neste aparelho": cookie assinado (HMAC com um segredo local em data/contas_segredo.bin, criado uma vez).
* Código de convite (TIL_CONVITE, pedido pelo script de apresentação): sem ele ninguém cria conta — evita estranhos.
* Google: usa o login nativo do Streamlit (`st.login`) quando `.streamlit/secrets.toml` tem a seção [auth] e o pacote
  Authlib está instalado (`python -m src.tools.configurar_login`). Sem isso, só as contas com senha aparecem.
* O dono vê tudo em Bastidores › 👥 Contas (no PC, ou pelo link entrando com o e-mail de TIL_DONO_EMAIL).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path("data/contas.db")
SECRET_PATH = Path("data/contas_segredo.bin")
COOKIE = "til_conta"
COOKIE_DAYS = 30
DDL = ("CREATE TABLE IF NOT EXISTS contas (email TEXT PRIMARY KEY, nome TEXT, metodo TEXT, salt BLOB, senha_hash BLOB, "
       "criado_em TEXT, ultimo_acesso TEXT, acessos INTEGER DEFAULT 0, situacao TEXT DEFAULT 'ativa')")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@contextmanager
def _conn(path: Optional[Path] = None):
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), timeout=10)
    try:
        c.execute(DDL)
        yield c
        c.commit()
    finally:
        c.close()


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _secret(path: Optional[Path] = None) -> bytes:
    p = Path(path or SECRET_PATH)
    if p.exists():
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    p.write_bytes(key)
    return key


def invite_required() -> bool:
    return bool(os.getenv("TIL_CONVITE", ""))


def _invite_ok(code: str) -> bool:
    exp = os.getenv("TIL_CONVITE", "")
    if not exp:
        return True
    return hmac.compare_digest(hashlib.sha256(str(code or "").strip().encode()).digest(),
                               hashlib.sha256(exp.strip().encode()).digest())


def create_account(nome: str, email: str, senha: str, convite: str = "", path: Optional[Path] = None) -> str:
    """'' se criou; senão a mensagem do problema (em português, sem revelar nada sensível)."""
    email = str(email or "").strip().lower()
    nome = str(nome or "").strip()
    if not nome or len(nome) < 2:
        return "Escreva o seu nome."
    if not EMAIL_RX.match(email):
        return "E-mail inválido."
    if len(senha or "") < 8:
        return "A senha precisa de pelo menos 8 caracteres."
    if not _invite_ok(convite):
        return "Código de convite incorreto — peça ao dono do laboratório."
    with _conn(path) as c:
        if c.execute("SELECT 1 FROM contas WHERE email = ?", (email,)).fetchone():
            return "Já existe conta com esse e-mail — use Entrar."
        salt = secrets.token_bytes(16)
        c.execute("INSERT INTO contas (email, nome, metodo, salt, senha_hash, criado_em, ultimo_acesso, acessos, situacao) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (email, nome[:80], "senha", salt, _hash(senha, salt), _now(), _now(), 1, "ativa"))
    return ""


def verify(email: str, senha: str, path: Optional[Path] = None) -> str:
    """'' se a senha confere e a conta está ativa; senão a mensagem."""
    email = str(email or "").strip().lower()
    with _conn(path) as c:
        r = c.execute("SELECT salt, senha_hash, situacao FROM contas WHERE email = ? AND metodo = 'senha'", (email,)).fetchone()
        if not r or not hmac.compare_digest(_hash(senha or "", r[0]), r[1]):
            return "E-mail ou senha incorretos."
        if r[2] != "ativa":
            return "Conta bloqueada pelo dono do laboratório."
        c.execute("UPDATE contas SET ultimo_acesso = ?, acessos = COALESCE(acessos, 0) + 1 WHERE email = ?", (_now(), email))
    return ""


def register_google(email: str, nome: str, path: Optional[Path] = None) -> str:
    email = str(email or "").strip().lower()
    if not email:
        return "O Google não informou o e-mail."
    with _conn(path) as c:
        r = c.execute("SELECT situacao FROM contas WHERE email = ?", (email,)).fetchone()
        if r and r[0] != "ativa":
            return "Conta bloqueada pelo dono do laboratório."
        if r:
            c.execute("UPDATE contas SET ultimo_acesso = ?, acessos = COALESCE(acessos, 0) + 1 WHERE email = ?", (_now(), email))
        else:
            c.execute("INSERT INTO contas (email, nome, metodo, criado_em, ultimo_acesso, acessos, situacao) "
                      "VALUES (?,?,?,?,?,?,?)", (email, str(nome or email)[:80], "google", _now(), _now(), 1, "ativa"))
    return ""


def is_active(email: str, path: Optional[Path] = None) -> bool:
    with _conn(path) as c:
        r = c.execute("SELECT situacao FROM contas WHERE email = ?", (str(email or "").lower(),)).fetchone()
    return bool(r and r[0] == "ativa")


def touch(email: str, path: Optional[Path] = None) -> None:
    with _conn(path) as c:
        c.execute("UPDATE contas SET ultimo_acesso = ?, acessos = COALESCE(acessos, 0) + 1 WHERE email = ?",
                  (_now(), str(email or "").lower()))


def list_accounts(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    with _conn(path) as c:
        rows = c.execute("SELECT nome, email, metodo, criado_em, ultimo_acesso, acessos, situacao FROM contas "
                         "ORDER BY criado_em DESC").fetchall()
    return [dict(zip(("nome", "email", "metodo", "criado_em", "ultimo_acesso", "acessos", "situacao"), r)) for r in rows]


def set_status(email: str, situacao: str, path: Optional[Path] = None) -> None:
    with _conn(path) as c:
        c.execute("UPDATE contas SET situacao = ? WHERE email = ?", (situacao, str(email or "").lower()))


def delete(email: str, path: Optional[Path] = None) -> None:
    with _conn(path) as c:
        c.execute("DELETE FROM contas WHERE email = ?", (str(email or "").lower(),))


# ------------------------------------------------------------------ cookie assinado (lembrar neste aparelho)
def make_token(email: str, days: int = COOKIE_DAYS, secret: Optional[bytes] = None) -> str:
    payload = f"{str(email).lower()}|{int(time.time()) + days * 86400}"
    sig = hmac.new(secret or _secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + sig


def read_token(token: str, secret: Optional[bytes] = None) -> Optional[str]:
    try:
        b64, sig = str(token).split(".", 1)
        payload = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode()
        good = hmac.new(secret or _secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]
        if not hmac.compare_digest(sig, good):
            return None
        email, exp = payload.rsplit("|", 1)
        return email if int(exp) >= time.time() else None
    except Exception:
        return None


# ------------------------------------------------------------------ Google (login nativo do Streamlit)
def google_ready() -> bool:
    try:
        import streamlit as st
        from streamlit.auth_util import is_authlib_installed

        return bool(is_authlib_installed() and "auth" in st.secrets)
    except Exception:
        return False


def owner_email() -> str:
    return os.getenv("TIL_DONO_EMAIL", "").strip().lower()
