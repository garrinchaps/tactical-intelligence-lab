"""Rodada 21 — Bastidores › 👥 Contas: quem criou conta e entrou pelo link (só o dono vê)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ui.components import styled_dataframe


def render_accounts() -> None:
    from src.ui import accounts as A
    from src.ui.gate import accounts_mode, is_owner

    st.markdown("## 👥 Contas de quem entra pelo link")
    if not is_owner():
        st.info("Só o dono do laboratório vê esta parte.")
        return
    st.caption("Cada pessoa cria a própria conta (e-mail e senha) ou entra com o Google. A senha nunca é guardada em "
               "texto — só um código embaralhado (scrypt). Bloquear tira o acesso na hora; apagar remove a conta.")
    if not accounts_mode():
        st.warning("O modo de contas está desligado nesta execução. O script de apresentação liga (TIL_CONTAS=1).")
    rows = A.list_accounts()
    k = st.columns(4)
    k[0].metric("Contas", len(rows))
    k[1].metric("Ativas", sum(1 for r in rows if r["situacao"] == "ativa"))
    k[2].metric("Pelo Google", sum(1 for r in rows if r["metodo"] == "google"))
    k[3].metric("Convite exigido", "sim" if A.invite_required() else "não")
    if not rows:
        st.info("Ninguém criou conta ainda.")
        return
    df = pd.DataFrame(rows).rename(columns={"nome": "Nome", "email": "E-mail", "metodo": "Como entra", "criado_em": "Criou em",
                                            "ultimo_acesso": "Último acesso", "acessos": "Acessos", "situacao": "Situação"})
    styled_dataframe(df, hide_index=True, width="stretch")
    with st.form("acc_admin", border=False):
        a, b = st.columns([3, 2])
        who = a.selectbox("Conta", [r["email"] for r in rows])
        act = b.radio("Ação", ["Bloquear", "Reativar", "Apagar"], horizontal=True)
        if st.form_submit_button("Aplicar", type="primary"):
            if act == "Apagar":
                A.delete(who)
            else:
                A.set_status(who, "bloqueada" if act == "Bloquear" else "ativa")
            st.rerun()
