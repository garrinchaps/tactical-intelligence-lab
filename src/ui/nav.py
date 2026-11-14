"""
Navegação por entidades: clicar em um jogo, time, jogador ou competição abre a tela dele; "← Voltar" volta
exatamente para onde você estava (pilha guardada na sessão).

    open_view("jogo", match_id=3869685)
    open_view("time", name="Flamengo")
    open_view("jogador", name="Lionel Messi")
    open_view("competicao", name="Premier League", season="2023/2024")
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

_PAGES: Dict[str, Any] = {}          # preenchido pelo app.py: {"buscar": Page, "jogo": Page, ...}
STACK = "nav_stack"
VIEW = "nav_view"


def register(pages: Dict[str, Any]) -> None:
    _PAGES.update(pages)


def current() -> Dict[str, Any]:
    return dict(st.session_state.get(VIEW) or {})


def param(key: str, default=None):
    return current().get(key, default)


def open_view(kind: str, **params) -> None:
    """Empilha a tela atual e abre a nova."""
    here = current()
    if here and here != {"kind": kind, **params}:
        st.session_state.setdefault(STACK, []).append(here)
        st.session_state[STACK] = st.session_state[STACK][-30:]
    st.session_state[VIEW] = {"kind": kind, **params}
    if kind == "jogo" and params.get("match_id"):
        if int(st.session_state.get("match_id", 0)) != int(params["match_id"]):
            st.session_state["team_focus"] = None
            st.session_state["chat_history"] = []
        st.session_state["match_id"] = int(params["match_id"])
    page = _PAGES.get(kind)
    if page is not None:
        st.switch_page(page)
    else:
        st.rerun()


def back() -> None:
    stack = st.session_state.get(STACK) or []
    prev: Optional[Dict[str, Any]] = stack.pop() if stack else None
    st.session_state[STACK] = stack
    if prev is None:
        prev = {"kind": "buscar"}
    st.session_state[VIEW] = prev
    if prev.get("kind") == "jogo" and prev.get("match_id"):
        st.session_state["match_id"] = int(prev["match_id"])
    page = _PAGES.get(prev.get("kind", "buscar")) or _PAGES.get("buscar")
    if page is not None:
        st.switch_page(page)
    else:
        st.rerun()


def back_button(label: str = "← Voltar", key: str = "nav_back") -> None:
    if st.button(label, key=key, type="secondary"):
        back()


def link(label: str, kind: str, key: str, help: Optional[str] = None, primary: bool = False, **params) -> None:
    """Botão que abre a tela da entidade."""
    if st.button(label, key=key, help=help, use_container_width=True, type="primary" if primary else "secondary"):
        open_view(kind, **params)
