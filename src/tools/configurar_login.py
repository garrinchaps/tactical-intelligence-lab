"""
Rodada 21 — configura o "Entrar com Google" (login nativo do Streamlit).

    python -m src.tools.configurar_login

Pede o link FIXO do app (ex.: https://seu-pc.algo.ts.net), o ID do cliente e o segredo do cliente criados no Google
Cloud Console (OAuth, aplicação Web) e grava em .streamlit/secrets.toml (arquivo FORA do Git). O segredo é digitado sem
aparecer na tela e nunca é impresso. O cookie_secret é gerado aqui, aleatório.
"""

from __future__ import annotations

import getpass
import secrets
from pathlib import Path

PATH = Path(".streamlit/secrets.toml")


def _toml_str(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(url: str, client_id: str, client_secret: str, cookie_secret: str) -> str:
    base = url.strip().rstrip("/")
    return ("[auth]\n"
            f"redirect_uri = {_toml_str(base + '/oauth2callback')}\n"
            f"cookie_secret = {_toml_str(cookie_secret)}\n\n"
            "[auth.google]\n"
            f"client_id = {_toml_str(client_id.strip())}\n"
            f"client_secret = {_toml_str(client_secret.strip())}\n"
            'server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"\n')


def main() -> None:
    try:
        from streamlit.auth_util import is_authlib_installed

        if not is_authlib_installed():
            print("Falta o pacote do login: rode  pip install Authlib  e depois este comando de novo.")
            return
    except Exception:
        pass
    if PATH.exists():
        ans = input(f"{PATH} já existe. Substituir? (s/N) ").strip().lower()
        if ans != "s":
            print("Nada foi alterado.")
            return
    url = input("Link FIXO do app (ex.: https://meu-pc.tail1234.ts.net): ").strip()
    if not url.startswith("https://"):
        print("O link precisa começar com https:// (o Google exige).")
        return
    cid = input("ID do cliente (Client ID) do Google: ").strip()
    sec = getpass.getpass("Segredo do cliente (Client secret) — não aparece na tela: ").strip()
    if not cid or not sec:
        print("ID e segredo são obrigatórios.")
        return
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(build(url, cid, sec, secrets.token_urlsafe(32)), encoding="utf-8")
    print(f"Pronto: login pelo Google configurado em {PATH} (fora do Git).")
    print(f"No Google Cloud Console, o 'URI de redirecionamento autorizado' tem que ser: {url.rstrip('/')}/oauth2callback")


if __name__ == "__main__":
    main()
