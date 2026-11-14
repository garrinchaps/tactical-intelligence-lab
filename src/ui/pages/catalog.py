"""Página 9 — Catálogo & Dados: base local, fontes, catálogo YAML, schema canônico, sincronização e arquivos de scout."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.canonical.provenance import ProvenanceRecord, ProvenanceRegistry
from src.canonical.schema import CANONICAL_AGGREGATE_SCHEMA, CANONICAL_EVENT_SCHEMA, schema_table
from src.connectors.catalog import CatalogError, CompetitionCatalog
from src.connectors.scout_file_parser import ScoutFileError, ScoutFileParser
from src.data_hub.registry import BADGES, SOURCES, DataLevel, provenance_base
from src.data_hub.sync import ALL_SOURCES, run_sync
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, kpi, note, page_header, provenance_panel
from src.ui.context import get_service, load_bundle

TEMPLATES = Path("data/templates")


def _fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _overview(reg: ProvenanceRegistry) -> None:
    svc = get_service()
    from src.ui.context import cached_catalog

    cat = cached_catalog()
    with svc.db.connect() as conn:
        with_events = conn.execute("SELECT COUNT(DISTINCT match_id) FROM events").fetchone()[0]
    by = cat["data_level"].value_counts() if not cat.empty else pd.Series(dtype=int)
    p = reg.register(ProvenanceRecord("db", "Base local", len(cat), "banco SQLite local (database/tactical_lab.db)",
                                      "MatchDatabase", "conforme cada fonte", "DERIVED", "contagem de linhas do catálogo"))
    c = st.columns(5)
    with c[0]:
        kpi("partidas no catálogo", _fmt(len(cat)), p)
    with c[1]:
        kpi("com eventos oficiais", _fmt(by.get(DataLevel.EVENTS, 0)), p)
    with c[2]:
        kpi("eventos já baixados (partidas)", _fmt(with_events), p)
    with c[3]:
        kpi("boxscore / placar", f"{_fmt(by.get(DataLevel.BOXSCORE, 0))} / {_fmt(by.get(DataLevel.RESULT, 0))}", p)
    with c[4]:
        dates = cat["match_date"][cat["match_date"].astype(str).str.len() >= 8] if not cat.empty else pd.Series(dtype=str)
        kpi("jogo mais recente", str(dates.max()) if not dates.empty else "—", p)
    if len(cat) < 500:
        note("Base pequena", "Clique em “Sincronizar agora” para trazer o catálogo completo do StatsBomb e da Wyscout.")

    st.markdown("#### Fontes e proveniência")
    status = svc.providers_status()
    rows = []
    for key, info in SOURCES.items():
        s = status.get(key, {})
        b = provenance_base(key)
        rows.append({"Fonte": info.label, "Conector": b["connector"], "Tier bruto": b["raw_tier"], "Nível": BADGES[info.level],
                     "Partidas": int((cat["data_source"] == key).sum()) if not cat.empty else 0,
                     "Situação": "ativa" if s.get("enabled") else f"desativada ({info.needs_key} no .env)",
                     "Licença": info.license_note})
    comparison_table(pd.DataFrame(rows), "Tier bruto: OFFICIAL = dado como publicado pela fonte; o que o laboratório calcula "
                     "a partir dele vira DERIVED; o gerador sintético é sempre SIMULATED.")

    st.markdown("#### Sincronizar")
    a, b, c2 = st.columns([2, 1, 1])
    chosen = a.multiselect("Fontes", ALL_SOURCES, default=ALL_SOURCES, format_func=lambda s: SOURCES[s].label if s in SOURCES else s)
    days = int(b.number_input("Dias para trás", min_value=1, max_value=30, value=3))
    prefetch = int(c2.number_input("Baixar eventos de N partidas", min_value=0, max_value=500, value=0))
    if st.button("🔄 Sincronizar agora", type="primary"):
        log, lines = st.empty(), []

        def say(msg):
            lines.append(msg)
            log.code("\n".join(lines[-14:]))
        with st.spinner("Sincronizando..."):
            run_sync(chosen, days, prefetch, service=svc, progress=say)
        load_bundle.clear()
        st.success("Sincronização concluída.")
    with st.expander("Atualização automática diária (Agendador de Tarefas do Windows)"):
        st.code('schtasks /Create /SC DAILY /ST 06:00 /TN "TacticalLabSync" /TR "cmd /c cd /d %CD% && '
                'venv\\Scripts\\python.exe -m src.data_hub.sync --days 3 --prefetch-events 20"', language="powershell")
    cov = svc.db.coverage()
    if not cov.empty:
        with st.expander("Cobertura por competição"):
            cov["data_level"] = cov["data_level"].map(lambda l: BADGES.get(l, l))
            comparison_table(cov)
    hist = svc.db.sync_history()
    if not hist.empty:
        with st.expander("Histórico de sincronizações"):
            comparison_table(hist)


def _yaml_catalog(reg: ProvenanceRegistry) -> None:
    st.markdown("#### Catálogo de competições (config/competitions.yaml)")
    note("Extensível sem código", "Para incluir uma competição, copie config/competitions.local.example.yaml para "
         "config/competitions.local.yaml e acrescente a entrada. O arquivo é validado ao abrir esta página.")
    try:
        cc = CompetitionCatalog.load()
    except CatalogError as exc:
        error_state("Catálogo inválido", exc, "Corrija o campo indicado no YAML.")
        return
    df = cc.to_frame()
    p = reg.register(ProvenanceRecord("yaml", "Catálogo YAML", len(df), ", ".join(cc.files), "CompetitionCatalog",
                                      "conforme cada fonte", "DERIVED", "entradas validadas do YAML"))
    k = st.columns(3)
    with k[0]:
        kpi("competições-temporadas", _fmt(len(df)), p)
    with k[1]:
        kpi("times distintos", _fmt(len(cc.teams())), p)
    with k[2]:
        kpi("arquivos lidos", len(cc.files), p)
    a, b, c = st.columns([2, 1, 1])
    q = a.text_input("Buscar competição, temporada ou time", "")
    fonte = b.selectbox("Fonte", ["todas", *sorted(df["fonte"].unique())] if not df.empty else ["todas"])
    nivel = c.selectbox("Nível", ["todos", *sorted(df["nivel_dado"].unique())] if not df.empty else ["todos"])
    res = cc.query(q, None if fonte == "todas" else fonte, None if nivel == "todos" else nivel)
    comparison_table(res.drop(columns=["times"], errors="ignore"), f"{len(res)} entradas.")
    if st.button("Gravar catálogo no banco (tabela competition_catalog)"):
        st.success(f"{cc.sync_to_sqlite()} entradas gravadas.")


def _schema() -> None:
    st.markdown("#### Schema canônico")
    note("Uma estrutura para todas as fontes", "Todo conector entrega este formato antes de qualquer métrica. Os cinco "
         "campos finais (proveniência) são obrigatórios: o teste em modo estrito falha se uma métrica aparecer sem eles.")
    a, b = st.columns(2)
    with a:
        st.markdown("**Eventos**")
        comparison_table(schema_table(CANONICAL_EVENT_SCHEMA))
    with b:
        st.markdown("**Agregados** (boxscore, arquivos de scout, estimativas simuladas)")
        comparison_table(schema_table(CANONICAL_AGGREGATE_SCHEMA))


def _scout_upload(reg: ProvenanceRegistry) -> None:
    st.markdown("#### Arquivos de scout do analista (xT por zona, matriz de passes, métricas de equipe)")
    note("Formatos aceitos", "CSV, JSON ou Excel (uma aba por tabela). O tipo é detectado pelas colunas; um erro cita "
         "arquivo, campo, valor e linha. Os modelos abaixo mostram as colunas esperadas.")
    if TEMPLATES.exists():
        cols = st.columns(4)
        for i, f in enumerate(sorted(TEMPLATES.glob("*.csv"))):
            cols[i % 3].download_button(f"⬇ {f.name}", f.read_bytes(), file_name=f.name, mime="text/csv", key=f"tpl_{f.name}")
        if (TEMPLATES / "LEIA-ME.md").exists():
            cols[3].download_button("⬇ LEIA-ME.md", (TEMPLATES / "LEIA-ME.md").read_bytes(), file_name="LEIA-ME.md")
    up = st.file_uploader("Arquivo de scout", type=["csv", "json", "xlsx"], key="scout_up")
    team = st.text_input("Equipe padrão (se o arquivo não tiver a coluna 'equipe')", "")
    if up is None:
        return
    try:
        out = ScoutFileParser.parse(up.getvalue(), up.name, default_team=team)
    except ScoutFileError as exc:
        error_state("Arquivo recusado", exc, "Compare as colunas com o modelo correspondente.")
        return
    except Exception as exc:
        error_state("Não foi possível ler o arquivo", exc)
        return
    canon = out["canonico"]
    p = reg.register(ProvenanceRecord("scout", f"Arquivo {up.name}", len(canon), f"arquivo do usuário: {up.name}",
                                      "ScoutFileParser", "do usuário", "DERIVED", "validado e mapeado ao schema de agregados"))
    st.success(f"{up.name}: {len(out['tabelas'])} tabela(s) válida(s), {len(canon)} linhas no schema canônico.")
    for kind, d in out["tabelas"].items():
        st.markdown(f"**Tabela: {kind}** — {len(d)} linhas")
        if kind == "xt_zonas":
            for t in d["equipe"].unique():
                st.plotly_chart(charts.heatmap_grid(ScoutFileParser.xt_grid(d, t), f"xT por zona — {t}", "xT"),
                                use_container_width=True)
        elif kind == "matriz_passes":
            for t in d["equipe"].unique():
                net = ScoutFileParser.pass_network(d, t)
                comparison_table(net["table"], f"{t}: grau ponderado e betweenness (distância = 1/passes).")
        else:
            comparison_table(d)
    with st.expander("Linhas no schema canônico (com proveniência)"):
        comparison_table(canon)
        kpi("linhas canônicas", len(canon), p)


@st.cache_data(show_spinner=False, ttl=600)
def _lake_table(name: str, version: str) -> pd.DataFrame:
    from src.data_lake.lake import Lake

    return Lake().read(name)


def _simonetti_view(lake, ver: str) -> None:
    """Tabelas coletadas do Simonetti Stats, com filtros por atleta, posição e clube."""
    from src.data_hub.sources.simonetti import player_team_columns
    from src.data_lake.build import simonetti_tables

    names = simonetti_tables(lake)
    if not names:
        return
    st.markdown("#### Simonetti Stats (coleta local para pesquisa)")
    pick = st.selectbox("Tabela", names, key="sm_tab")
    d = _lake_table(pick, ver)
    pcol, tcol = player_team_columns(d)
    poscol = next((c for c in d.columns if c.lower() in ("posicao", "posição", "position", "pos")), None)
    a, b, c = st.columns(3)
    q = a.text_input("Atleta contém", "", key="sm_q") if pcol else ""
    clubs = ["todos"] + sorted(d[tcol].dropna().astype(str).unique()) if tcol else ["todos"]
    club = b.selectbox("Clube", clubs, key="sm_club")
    poss = ["todas"] + sorted(d[poscol].dropna().astype(str).unique()) if poscol else ["todas"]
    pos = c.selectbox("Posição", poss, key="sm_pos")
    f = d
    if pcol and q.strip():
        f = f[f[pcol].astype(str).str.contains(q.strip(), case=False, regex=False)]
    if tcol and club != "todos":
        f = f[f[tcol].astype(str) == club]
    if poscol and pos != "todas":
        f = f[f[poscol].astype(str) == pos]
    comparison_table(f.drop(columns=[x for x in ("fonte", "conector", "licenca", "ingestao_utc", "arquivo_origem")
                                     if x in f.columns]).head(500),
                     f"{len(f)} de {len(d)} linhas · fonte: Simonetti Stats (dados de provedores não identificados pelo "
                     "site) · uso local de pesquisa, não redistribuir.")


def _unified(reg: ProvenanceRegistry) -> None:
    from src.data_lake.lake import Lake, status

    st.markdown("#### Base unificada (data/lake) e mapeamento de IDs entre fontes")
    stt = status()
    note("Formato", f"Arquivos {'Parquet' if stt['parquet'] else 'CSV comprimido (instale pyarrow para Parquet)'} em "
         f"{stt['pasta']}; DuckDB {'ativo (data/lake/til.duckdb)' if stt['duckdb'] else 'opcional (pip install duckdb)'}; "
         "espelho no banco do app (tabelas lake_*). Atualização diária automática.")
    lake = Lake()
    tabs = lake.tables()
    if tabs.empty:
        empty_state("A base unificada ainda está vazia", "Rode a sincronização das fontes externas uma vez.", "🧩",
                    "python -m src.data_hub.sync --only transfermarkt understat lake")
        return
    p = reg.register(ProvenanceRecord("lake", "Base unificada", int(tabs["linhas"].fillna(0).sum()), "data/lake",
                                      "Lake", "conforme cada fonte", "DERIVED", "soma das linhas das tabelas do lake"))
    ver = str(tabs["MB"].sum()) + str(len(tabs))
    k = st.columns(4)
    dt = _lake_table("dim_teams", ver) if lake.exists("dim_teams") else pd.DataFrame()
    dp = _lake_table("dim_players", ver) if lake.exists("dim_players") else pd.DataFrame()
    with k[0]:
        kpi("tabelas no lake", len(tabs), p)
    with k[1]:
        kpi("linhas no total", _fmt(tabs["linhas"].fillna(0).sum()), p)
    with k[2]:
        kpi("clubes/seleções (dim_teams)", _fmt(len(dt)), p)
    with k[3]:
        kpi("atletas (dim_players)", _fmt(len(dp)), p)
    comparison_table(tabs, "us_* = Understat · tm_* = Transfermarkt · af_* = API-Futebol · apf_* = API-Football · "
                     "bd_* = Base dos Dados · dim_*/…_ids = mapeamento de identificadores.")
    if not dt.empty:
        q = st.text_input("Ver como um clube aparece em cada fonte", "Manchester United", key="dim_q")
        from src.data_lake.ids import team_core, slug

        hit = dt[dt["team_key"].str.contains(slug(team_core(q)), regex=False) |
                 dt["nomes_alternativos"].str.lower().str.contains(q.lower(), regex=False)] if q.strip() else dt.head(20)
        cols = ["team_key", "nome", "pais", "n_fontes", "nomes_alternativos"] + [c for c in dt.columns if c.endswith("_id")]
        comparison_table(hit[cols].head(20), "Uma linha por clube; cada coluna *_id é o identificador daquela fonte.")
    _simonetti_view(lake, ver)
    for name, title in (("apf_classificacao", "Classificação (API-Football)"), ("af_classificacao", "Classificação (API-Futebol)"),
                        ("apf_calendario", "Próximos jogos (API-Football)")):
        if lake.exists(name):
            with st.expander(title):
                comparison_table(_lake_table(name, ver))


def render(_ctx=None) -> None:
    page_header("🗄️ Catálogo & Dados", "O que existe na base, de onde vem, em que formato entra e como adicionar mais.")
    reg = ProvenanceRegistry()
    t1, t5, t2, t3, t4 = st.tabs(["📦 Base & sincronização", "🧩 Base unificada", "📚 Catálogo YAML", "🧬 Schema canônico",
                                  "📁 Arquivos de scout"])
    with t5:
        try:
            _unified(reg)
        except Exception as exc:
            error_state("Base unificada indisponível", exc)
    with t1:
        try:
            _overview(reg)
        except Exception as exc:
            error_state("Base local indisponível", exc)
    with t2:
        _yaml_catalog(reg)
    with t3:
        _schema()
    with t4:
        _scout_upload(reg)
    provenance_panel(reg)
