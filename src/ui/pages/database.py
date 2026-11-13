"""Seção 🗄️ Base de Dados — cobertura, fontes, sincronização e catálogo."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data_hub.registry import BADGES, SOURCES, DataLevel
from src.data_hub.sync import ALL_SOURCES, run_sync
from src.ui.components import kpi, section_header
from src.ui.context import get_service, load_bundle


def render(_ctx=None) -> None:
    section_header("🗄️ Base de Dados", "O que existe na base local, de onde vem e como mantê-la atualizada.")
    svc = get_service()
    cat = svc.db.catalog()
    with svc.db.connect() as conn:
        with_events = conn.execute("SELECT COUNT(DISTINCT match_id) FROM events").fetchone()[0]
    c = st.columns(5)
    by_level = cat["data_level"].value_counts() if not cat.empty else pd.Series(dtype=int)
    with c[0]:
        kpi("partidas no catálogo", f"{len(cat):,}".replace(",", "."))
    with c[1]:
        kpi("com eventos oficiais", f"{int(by_level.get(DataLevel.EVENTS, 0)):,}".replace(",", "."))
    with c[2]:
        kpi("eventos já baixados", f"{with_events:,}".replace(",", "."))
    with c[3]:
        kpi("boxscore / placar", f"{int(by_level.get(DataLevel.BOXSCORE, 0))} / {int(by_level.get(DataLevel.RESULT, 0))}")
    with c[4]:
        dates = cat["match_date"][cat["match_date"].astype(str).str.len() >= 8] if not cat.empty else pd.Series(dtype=str)
        kpi("jogo mais recente", str(dates.max()) if not dates.empty else "—")

    if len(cat) < 500:
        st.info("A base ainda está pequena. Clique em **Sincronizar agora** para trazer o catálogo completo do "
                "StatsBomb (~3.960 partidas) e da Wyscout (1.941 partidas) — leva poucos minutos na primeira vez.")

    st.markdown("##### Fontes")
    status = svc.providers_status()
    rows = []
    for key, info in SOURCES.items():
        st_ = status.get(key, {})
        n = int((cat["data_source"] == key).sum()) if not cat.empty else 0
        rows.append({"Fonte": info.label, "Nível": BADGES[info.level], "Partidas": n,
                     "Situação": "ativa" if st_.get("enabled") else f"desativada ({info.needs_key} no .env)",
                     "Cota hoje": st_.get("quota_left", "—") if key == "api_football" else "—",
                     "Licença / observação": info.license_note})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("##### Sincronizar")
    a, b, c2 = st.columns([2, 1, 1])
    chosen = a.multiselect("Fontes", ALL_SOURCES, default=ALL_SOURCES,
                           format_func=lambda s: SOURCES[s].label if s in SOURCES else s)
    days = int(b.number_input("Dias para trás (jogos recentes)", min_value=1, max_value=30, value=3))
    prefetch = int(c2.number_input("Baixar eventos de N partidas", min_value=0, max_value=500, value=0,
                                   help="Alimenta a base de referência de Pontos Fortes e Fracos."))
    if st.button("🔄 Sincronizar agora", type="primary"):
        log = st.empty()
        lines = []

        def say(msg):
            lines.append(msg)
            log.code("\n".join(lines[-14:]))

        with st.spinner("Sincronizando..."):
            run_sync(chosen, days, prefetch, service=svc, progress=say)
        load_bundle.clear()
        st.success("Sincronização concluída.")

    with st.expander("Atualização automática diária (Agendador de Tarefas do Windows)"):
        st.markdown(
            "Rode uma vez no PowerShell, **na pasta do projeto**, para agendar a sincronização todo dia às 6h:\n"
            "```powershell\n"
            "schtasks /Create /SC DAILY /ST 06:00 /TN \"TacticalLabSync\" /TR "
            "\"cmd /c cd /d %CD% && venv\\Scripts\\python.exe -m src.data_hub.sync --days 3 --prefetch-events 20\"\n"
            "```\n"
            "Para remover: `schtasks /Delete /TN TacticalLabSync /F`")

    st.markdown("##### Cobertura por competição")
    cov = svc.db.coverage()
    if not cov.empty:
        cov["data_level"] = cov["data_level"].map(lambda l: BADGES.get(l, l))
        st.dataframe(cov.rename(columns={"data_source": "fonte", "data_level": "nível", "competition_name": "competição",
                                         "season_name": "temporada"}), use_container_width=True, hide_index=True)

    st.markdown("##### Histórico de sincronizações")
    hist = svc.db.sync_history()
    if hist.empty:
        st.caption("Nenhuma sincronização registrada ainda.")
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
