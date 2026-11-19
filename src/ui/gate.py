"""
Rodada 18 — porta de entrada para a versão PÚBLICA (apresentação).

* Quem abre no próprio PC (localhost / 127.0.0.1) entra direto, com tudo liberado — como sempre.
* Quem chega pelo LINK PÚBLICO (túnel da Cloudflare, Tailscale, Streamlit Cloud) é "visitante":
  - precisa da senha de apresentação se `TIL_SENHA` estiver definida (variável de ambiente do processo ou
    `st.secrets`) — a senha nunca é impressa, registrada nem comparada em texto puro (hash + compare_digest);
  - não dispara nada pesado (atualizações, downloads, treinos, recálculos): `visitor_blocked()` devolve True e a tela
    mostra um aviso no lugar do botão.
* `TIL_MODO_PUBLICO=1` trata TODO acesso como visitante (útil em servidor, onde não existe "o PC do dono").
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0")


def public_mode() -> bool:
    return os.getenv("TIL_MODO_PUBLICO", "0").strip().lower() in ("1", "true", "sim", "yes")


PROXY_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-host", "x-real-ip", "forwarded",
                 "tailscale-user-login", "tailscale-funnel-request")


def _headers() -> dict:
    try:
        import streamlit as st

        return {str(k).lower(): v for k, v in dict(st.context.headers).items()}
    except Exception:
        return {}


def is_visitor(headers: dict | None = None) -> bool:
    """True para quem chega de fora do PC (link público) ou para todos no modo público. Qualquer cabeçalho de
    intermediário (Cloudflare, Tailscale, proxy) já conta como visitante, mesmo que o Host pareça local."""
    if public_mode():
        return True
    hd = _headers() if headers is None else {str(k).lower(): v for k, v in headers.items()}
    if any(k in hd for k in PROXY_HEADERS):
        return True
    h = str(hd.get("host", "")).strip().lower()
    h = h.split("]")[0] + "]" if h.startswith("[") else h.split(":")[0]
    return bool(h) and h not in LOCAL_HOSTS


def _expected() -> str:
    v = os.getenv("TIL_SENHA", "")
    if not v:
        try:
            import streamlit as st

            v = str(st.secrets.get("TIL_SENHA", "") or "")
        except Exception:
            v = ""
    return v


def password_defined() -> bool:
    return bool(_expected())


def check(typed: str, expected: str | None = None) -> bool:
    exp = _expected() if expected is None else expected
    if not exp:
        return False
    a = hashlib.sha256(str(typed or "").encode("utf-8")).digest()
    b = hashlib.sha256(exp.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


COOKIE = "til_acesso"
COOKIE_HOURS = 12


def token(day: str | None = None, expected: str | None = None) -> str:
    """Marca de acesso do dia, DERIVADA da senha (HMAC) — a senha nunca vai para o cookie. Trocar a senha invalida."""
    exp = _expected() if expected is None else expected
    day = day or time.strftime("%Y-%m-%d")
    return hmac.new(exp.encode("utf-8"), f"til-gate|{day}".encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def cookie_ok(value: str | None, expected: str | None = None) -> bool:
    """Aceita a marca de hoje ou de ontem (sessão que passou da meia-noite)."""
    exp = _expected() if expected is None else expected
    if not value or not exp:
        return False
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    return any(hmac.compare_digest(str(value), token(d, exp)) for d in (today, yesterday))


def _remember_visitor() -> None:
    """Grava o cookie (mesma origem do app) para a recarga do celular não pedir a senha de novo por 12 h."""
    try:
        import streamlit.components.v1 as components

        components.html(f"<script>document.cookie='{COOKIE}={token()}; path=/; max-age={COOKIE_HOURS * 3600}; "
                        "SameSite=Lax; Secure';</script>", height=0)
    except Exception:
        pass


def _cookie_value() -> str | None:
    try:
        import streamlit as st

        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


def visitor_blocked(what: str = "Esta ação") -> bool:
    """Chame antes de qualquer botão pesado. Visitante: mostra o aviso e devolve True (não execute)."""
    if not is_visitor():
        return False
    try:
        import streamlit as st

        st.info(f"🔒 {what} fica desligada na versão de apresentação (só no PC do laboratório).")
    except Exception:
        pass
    return True


def require() -> None:
    """Chamado no topo do app. Visitante sem senha certa não passa daqui."""
    import streamlit as st

    if not is_visitor():
        return
    if st.session_state.get("_gate_ok"):
        if st.session_state.pop("_gate_set_cookie", False):
            _remember_visitor()
        return
    if password_defined() and cookie_ok(_cookie_value()):     # já entrou neste aparelho nas últimas 12 h
        st.session_state["_gate_ok"] = True
        return
    if not password_defined():
        if public_mode():                                # servidor sem senha configurada: aberto, mas avisa
            st.session_state["_gate_ok"] = True
        else:                                            # link do PC sem senha: não abre (protege o PC)
            st.error("Versão de apresentação sem senha configurada. Rode o script de apresentação, que pede a senha.")
            st.stop()
        return
    st.markdown("<div style='max-width:420px;margin:12vh auto 0 auto'>"
                "<h2 style='color:#22D3EE;margin-bottom:0'>Tactical Intelligence Lab</h2>"
                "<p style='color:#94A3B8'>Laboratório de análise tática · versão de apresentação</p></div>",
                unsafe_allow_html=True)
    fails = int(st.session_state.get("_gate_fails", 0))
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form("til_gate"):
            typed = st.text_input("Senha de acesso", type="password")
            ok = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if ok:
            if fails >= 5:
                time.sleep(min(10, fails))               # tentativa repetida fica lenta (sem bloquear o servidor todo)
            if check(typed):
                st.session_state["_gate_ok"] = True
                st.session_state["_gate_set_cookie"] = True
                st.session_state.pop("_gate_fails", None)
                st.rerun()
            st.session_state["_gate_fails"] = fails + 1
            st.error("Senha incorreta.")
    st.stop()
