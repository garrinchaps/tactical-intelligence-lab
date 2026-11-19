"""
TACTICAL INTELLIGENCE LAB — aplicação Streamlit.

Navegação no topo (pílulas) + UMA caixa de busca:
  💬 Assistente (chat: a pergunta pode trazer o jogo junto) · 🔎 Buscar (jogos, times, jogadores, competições) · 🆚 Comparar
  Telas abertas pelo clique (só o item na tela, com "← Voltar"): jogo · time · jogador · competição
  ⚙️ Bastidores (separado do programa): como a IA aprende, ML & avaliação, analista técnico, dados & fontes, laboratório

Execução: streamlit run app.py
"""

from __future__ import annotations

from importlib import import_module
from typing import Callable

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Tactical Intelligence Lab", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")

from src.data_hub.registry import BADGES, DataLevel  # noqa: E402
from src.ui import theme  # noqa: E402
from src.ui import nav  # noqa: E402
from src.ui.i18n import LANGS, t  # noqa: E402

def _lazy_page(module_name: str, function_name: str = "render") -> Callable:
    """Importa cada página somente quando ela é aberta, sem carregar todo o app no boot."""
    def call(*args, **kwargs):
        module = import_module(f"src.ui.pages.{module_name}")
        return getattr(module, function_name)(*args, **kwargs)
    call.__name__ = f"{module_name}_{function_name}"
    call.__module__ = f"src.ui.pages.{module_name}"
    return call


DEFAULT_MATCH_ID = 3869685  # final da Copa do Mundo 2022 (StatsBomb) — disponível offline em data/demo


# ------------------------------------------------------------------ contexto da partida
def current_context(with_sim_ci: bool = True):
    """Abre a partida da sessão e monta o contexto (None + estado de erro desenhado se falhar)."""
    from src.ui.context import build_context, load_bundle, teams_of
    from src.ui.components import empty_state, error_state
    if not st.session_state.get("match_id"):
        empty_state("Nenhum jogo aberto", "Cite o jogo na pergunta (times e ano) ou abra um pelo 🔎 Buscar.", "🏟️")
        return None
    try:
        bundle = load_bundle(int(st.session_state["match_id"]))
    except Exception as exc:
        error_state(f"Não foi possível abrir a partida {st.session_state['match_id']}", exc,
                    "Use “Trocar partida” no topo ou sincronize a base em Bastidores → Dados & Fontes.")
        return None
    upload_df = st.session_state.get("upload_df") if bundle.level == DataLevel.UPLOAD else None
    teams = teams_of(bundle, upload_df if upload_df is not None else bundle.events)
    if st.session_state.get("team_focus") not in teams and teams:
        st.session_state["team_focus"] = teams[0]
    try:
        return build_context(bundle, st.session_state.get("team_focus"), upload_df=upload_df, with_sim_ci=with_sim_ci)
    except Exception as exc:
        error_state("Erro ao processar a partida", exc)
        return None


def match_bar() -> None:
    """Faixa da partida aberta + equipe em foco + atalho para analisar o jogo ou trocar (pela busca)."""
    from src.ui.context import load_bundle, teams_of
    from src.ui.components import match_strip
    if not st.session_state.get("match_id"):
        return                                           # rodada 20: sem jogo aberto, sem faixa (nada é carregado)
    try:
        bundle = load_bundle(int(st.session_state["match_id"]))
    except Exception:
        bundle = None
    a, b, c = st.columns([5.2, 2.4, 1.4])
    with a:
        if bundle is not None:
            match_strip(bundle.meta or {}, BADGES.get(bundle.level, bundle.level))
    with b:
        if bundle is not None:
            teams = teams_of(bundle, bundle.events)
            if teams:
                cur = st.session_state.get("team_focus")
                st.session_state["team_focus"] = st.radio("Equipe em foco", teams, index=teams.index(cur) if cur in teams else 0,
                                                          horizontal=True, key="team_focus_radio", label_visibility="collapsed")
    with c:
        if st.button(t("🏟️ Abrir o jogo"), use_container_width=True, key="bar_open_game",
                     help="Tela do jogo com todas as seções. Para trocar de jogo, cite-o na pergunta ou use a busca."):
            nav.open_view("jogo", match_id=int(st.session_state["match_id"]))


def needs_match(render: Callable, needs_events: bool = False) -> Callable[[], None]:
    def page() -> None:
        match_bar()
        ctx = current_context()
        if ctx is None:
            return
        if needs_events and not ctx.has_events:
            from src.ui.components import empty_state
            empty_state("Esta seção precisa de eventos com coordenadas", f"A partida aberta tem nível {ctx.bundle.level}.",
                        "🗺️", "Troque para uma partida ✅ (eventos StatsBomb/Wyscout).")
            return
        render(ctx)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


def standalone(render: Callable, pass_ctx: bool = False) -> Callable[[], None]:
    def page() -> None:
        # rodada 20: sem jogo aberto, a tela abre sem o aviso "Nenhum jogo aberto" (o jogo é opcional nela)
        render(current_context(with_sim_ci=False) if pass_ctx and st.session_state.get("match_id") else None)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


def _named(fn: Callable, name: str) -> Callable:
    fn.__name__ = name
    return fn


assistant_render = _lazy_page("assistant")
search_render = _lazy_page("search_all")
compare_render = _lazy_page("compare", "render_page")
squad_render = _lazy_page("squad")
scout_render = _lazy_page("scout")
rankings_render = _lazy_page("rankings")
games_render = _lazy_page("games")
clubs_render = _lazy_page("clubs")
players_render = _lazy_page("players_search")
competition_render = _lazy_page("competition")
neural_render = _lazy_page("neural")
ml_render = _lazy_page("ml_inspection")
ai_analyst_render = _lazy_page("ai_analyst")
catalog_render = _lazy_page("catalog")
lab_render = _lazy_page("lab")


MAIN = [
    st.Page(_named(lambda: assistant_render(current_context, match_bar), "page_assistente"), title="Assistente", icon="💬",
            url_path="assistente", default=True),
    st.Page(standalone(search_render), title="Buscar", icon="🔎", url_path="buscar"),
    st.Page(_named(lambda: compare_render(current_context, match_bar), "page_comparar"), title="Comparar", icon="🆚",
            url_path="comparar"),
    st.Page(standalone(squad_render), title="Escalação", icon="📋", url_path="escalacao"),
    st.Page(standalone(scout_render), title="Scout", icon="🎯", url_path="scout"),
    st.Page(standalone(rankings_render), title="Rankings", icon="🏆", url_path="rankings"),
]
VIEWS = {   # telas abertas pelo clique (fora do menu)
    "jogo": st.Page(_named(lambda: games_render(current_context), "page_jogo"), title="Jogo", icon="🏟️", url_path="jogo"),
    "time": st.Page(standalone(clubs_render), title="Time", icon="🛡️", url_path="time"),
    "jogador": st.Page(standalone(players_render), title="Jogador", icon="👤", url_path="jogador"),
    "competicao": st.Page(standalone(competition_render), title="Competição", icon="🏆", url_path="competicao"),
}
BACKSTAGE = [
    st.Page(standalone(neural_render, pass_ctx=True), title="IA do laboratório (treino e bastidores)", icon="🧠", url_path="como-a-ia-aprende"),
    st.Page(needs_match(ml_render), title="Machine Learning & Avaliação", icon="🤖", url_path="ml"),
    st.Page(needs_match(ai_analyst_render), title="Analista técnico (guard)", icon="🛡️", url_path="analista-tecnico"),
    st.Page(standalone(catalog_render), title="Dados & Fontes", icon="🗄️", url_path="dados"),
    st.Page(standalone(lab_render), title="Laboratório", icon="🧪", url_path="laboratorio"),
]


def _logo(col) -> None:
    if col.button("⚽ Tactical Intelligence Lab", key="til_logo_home", help="Voltar ao início",
                  use_container_width=True):
        st.session_state[nav.STACK] = []
        nav.open_view("assistente")


def _go_search() -> None:
    st.session_state["_do_search"] = True


def top_bar(focused: bool = False) -> None:
    """Navegação global, busca, histórico rápido e modo de foco."""
    if st.session_state.get("til_focus_mode"):
        a, b = st.columns([8, 1])
        _logo(a)
        if b.button("✕ Sair do foco", use_container_width=True, key="til_focus_exit"):
            st.session_state["til_focus_mode"] = False
            st.rerun()
        st.markdown('<div class="til-glow"></div>', unsafe_allow_html=True)
        return
    if focused:
        a, b = st.columns([7, 1])
        _logo(a)
        if b.button("⛶ Foco", key="til_focus_enter_focused"):
            st.session_state["til_focus_mode"] = True
            st.rerun()
        st.markdown('<div class="til-glow"></div>', unsafe_allow_html=True)
        return
    cols = st.columns([2.3] + [1.15] * len(MAIN) + [1.35])
    _logo(cols[0])
    for col, page in zip(cols[1:], MAIN):
        col.page_link(page, label=t(page.title), icon=page.icon, use_container_width=True)
    with cols[-1].popover(t("⚙️ Bastidores"), use_container_width=True):
        st.caption(t("Como tudo foi feito — separado do programa."))
        for page in BACKSTAGE:
            st.page_link(page, label=t(page.title), icon=page.icon)
        from src.ui import gate as _gate                 # rodada 21: quem entrou pelo link vê a conta e pode sair

        _u = _gate.current_user()
        if _u.get("email"):
            st.caption(f"Conectado como {_u['email']}")
            if st.button("Sair da conta", key="til_logout"):
                _gate.logout()
                st.rerun()
        # rodada 20: idioma e situação da base saíram do topo de todas as telas (ficam aqui, sem ocupar espaço)
        st.session_state.setdefault("w_lang", st.session_state.get("_lang", "pt"))
        st.selectbox(t("Idioma"), list(LANGS), format_func=LANGS.get, key="w_lang",
                     on_change=lambda: st.session_state.__setitem__("_lang", st.session_state["w_lang"]),
                     help="Idioma da interface (as respostas do Assistente continuam em português).")
        try:
            from src.data_hub import autosync
            from src.ui.context import get_service

            last = st.session_state.get("_perf_last")
            st.caption(autosync.status_text(autosync.ensure_started(get_service().db)) + "  ·  " + _app_version()
                       + (f"  ·  ⚡ última tela {last[1]:.1f} s" if last else ""))
            fm = autosync.fotmob_status()
            if fm:
                st.caption(fm)
        except Exception:
            pass
    st.markdown('<div class="til-glow"></div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _app_version() -> str:
    """Branch + commit em uso (lidos do .git, sem rodar git): confirma na tela qual versão está aberta."""
    from pathlib import Path

    try:
        head = Path(".git/HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1]
            branch = ref.rsplit("/", 1)[-1] if "/" not in ref[11:] else ref[11:]
            p = Path(".git") / ref
            sha = p.read_text(encoding="utf-8").strip() if p.exists() else next(
                (ln.split()[0] for ln in Path(".git/packed-refs").read_text(encoding="utf-8").splitlines()
                 if ln.endswith(ref)), "")
            return f"versão: {branch} · {sha[:7]}"
        return f"versão: {head[:7]}"
    except Exception:
        return "versão: rodada 8"


def main() -> None:
    theme.inject_theme()
    try:                                                 # rodada 11: avisa o processo de fundo que a tela está em uso
        from src.data_hub import activity

        activity.touch()
    except Exception:
        pass
    # rodada 20: nenhum jogo pré-carregado (antes abria a final da Copa 2022 em toda sessão, sem ninguém pedir)
    recent = st.session_state.setdefault("recent_match_ids", [])
    if st.session_state.get("match_id"):
        current_mid = int(st.session_state["match_id"])
        recent = [current_mid] + [int(x) for x in recent if int(x) != current_mid]
        st.session_state["recent_match_ids"] = recent[:5]
    st.session_state.setdefault("chat_history", [])
    page = st.navigation(MAIN + list(VIEWS.values()) + BACKSTAGE, position="hidden")
    from src.ui import gate                              # rodada 18: link público pede senha; no PC entra direto

    gate.require()                                       # depois do menu: o visitante cai na tela que pediu
    from src.ui import loading, warmup                   # rodada 19: pré-aquecimento + tela de carregamento

    if not loading.splash_gate(warmup.start()):
        return
    _cover = st.empty()                                  # cobertura de carregamento (só aparece se passar de 0,35 s)
    _cover.markdown(loading.overlay_html(getattr(page, "url_path", "") or ""), unsafe_allow_html=True)
    nav.register({"buscar": MAIN[1], "assistente": MAIN[0], "comparar": MAIN[2], "escalacao": MAIN[3],
                   "scout": MAIN[4], "rankings": MAIN[5], "treino": BACKSTAGE[0], **VIEWS})
    goto = st.session_state.pop("goto", None)            # pedidos antigos de "abrir em Jogos" viram a tela do jogo
    if goto:
        if goto == "jogos" and st.session_state.get("match_id"):
            nav.open_view("jogo", match_id=int(st.session_state["match_id"]))
        else:
            st.switch_page({"assistente": MAIN[0], "comparar": MAIN[2], "buscar": MAIN[1]}.get(goto, MAIN[0]))
    focused = getattr(page, "url_path", "") in {p.url_path for p in VIEWS.values()}
    if not focused:                                      # página do menu = ponto de partida do "← Voltar"
        key = {"assistente": "assistente", "buscar": "buscar", "comparar": "comparar",
               "escalacao": "escalacao", "scout": "scout", "rankings": "rankings"}.get(getattr(page, "url_path", ""))
        if key and nav.current().get("kind") != key:
            st.session_state[nav.VIEW] = {"kind": key, **({"q": st.session_state.get("_last_q", "")} if key == "buscar" else {})}
    top_bar(focused)
    if not focused:                                      # a atualização automática continua sendo ligada (sem texto)
        try:
            from src.data_hub import autosync
            from src.ui.context import get_service

            autosync.ensure_started(get_service().db)
        except Exception:
            pass
    import time as _time

    from src.ui import perf as _perf

    _t0 = _time.perf_counter()
    try:
        page.run()
    finally:                                              # rodada 16: tempo de cada tela (monitor de velocidade)
        _cover.empty()
        _dt = _time.perf_counter() - _t0
        _name = getattr(page, "url_path", "") or getattr(page, "title", "?")
        _perf.record("tela", _name, _dt)
        st.session_state["_perf_last"] = (_name, _dt)


main()
