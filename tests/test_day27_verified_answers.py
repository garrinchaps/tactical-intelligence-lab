"""v27: etiquetas [EXATO]/[DERIVADO]/[SEM ORIGEM] na tela e Gemini com teto rígido + troca de modelo + fallback local."""
import sys
import types

import pytest

from src.guard.present import present, tag_numbers

EV = {"metadata": {"placar": "A 2 x 1 B", "match_player_roster": ["Saka"]},
      "blocos": {"estatisticas_dos_times": {"Finalizações": {"A": 18, "B": 7}, "Finalizações no gol": {"A": 8, "B": 2}}}}


def test_every_number_is_tagged_and_untraceable_is_hidden():
    txt = ("| Estatística | A | B |\n|---|---|---|\n| Finalizações | 18 | 7 |\n| Inventada | 99 | 3 |\n\n"
           "Volume: 18 x 7; precisão de 44% no alvo. Na Copa de 2022 houve algo. Ele deu 977 passes errados.")
    out, n = tag_numbers(txt, EV)
    assert "18 [EXATO]" in out and "7 [EXATO]" in out and "44% [DERIVADO]" in out
    assert "99" not in out and "Inventada" not in out and "977" not in out     # linha e frase sem origem somem
    assert "2022 [" not in out and "Copa de 2022" in out                         # ano não é métrica
    assert n["sem_origem"] == 2 and n["ocultadas"] == 2 and "ocultados pelo verificador" in out
    assert "[SEM ORIGEM]" not in out                                             # nunca aparece na tela


def test_bold_numbers_and_present_keeps_raw():
    res = {"report_markdown": "Finalizações: **18** contra **7**.", "evidence": EV}
    present(res, show_tags=True)
    assert "**18** [EXATO]" in res["report_markdown"] and res["report_raw"] == "Finalizações: **18** contra **7**."
    assert present(res, show_tags=True) is res and res["report_markdown"].count(" [EXATO]") == 2 + 1   # idempotente
    assert present({"report_markdown": "Olá!", "evidence": None})["report_markdown"] == "Olá!"


# ---------------------------------------------------------------- Gemini
def _fake_genai(monkeypatch, behaviour):
    calls = []

    class Models:
        def __init__(self, timeout):
            self.timeout = timeout

        def generate_content(self, model, contents, config):
            calls.append((model, self.timeout))
            return behaviour(model)

        def list(self):
            return []

    class Client:
        def __init__(self, api_key, http_options=None):
            self.models = Models(getattr(http_options, "timeout", None))

    types_mod = types.SimpleNamespace(HttpOptions=lambda timeout: types.SimpleNamespace(timeout=timeout),
                                      GenerateContentConfig=lambda **k: k)
    genai = types.SimpleNamespace(Client=Client, types=types_mod)
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)
    return calls


@pytest.fixture()
def analyst(monkeypatch):
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst as D

    monkeypatch.setattr(D, "_working_model", None)
    monkeypatch.setattr(D, "_dead_models", set())
    monkeypatch.setattr(D, "_discovered", [])
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    return D(api_key="chave-falsa-para-teste-0123456789")


def test_gemini_skips_dead_models_and_remembers_the_working_one(monkeypatch, analyst):
    def beh(model):
        if model == "gemini-2.5-flash":
            raise RuntimeError("404 NOT_FOUND model")
        return types.SimpleNamespace(text="ok")
    calls = _fake_genai(monkeypatch, beh)
    assert analyst._llm("s", "p") == "ok"
    assert [c[0] for c in calls] == ["gemini-2.5-flash", "gemini-flash-latest"]
    assert all(c[1] is not None and c[1] <= 60_000 for c in calls)       # cada tentativa com tempo-limite
    calls.clear()
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst as D

    assert D(api_key="chave-falsa-para-teste-0123456789")._llm("s", "p") == "ok"
    assert [c[0] for c in calls] == ["gemini-flash-latest"]              # vai direto no que funcionou


def test_gemini_hard_budget_raises_timeout(monkeypatch, analyst):
    import time as _t

    clock = {"t": 1000.0}
    monkeypatch.setattr(_t, "time", lambda: clock["t"])

    def beh(model):
        clock["t"] += 61                                                  # a 1ª tentativa estoura o orçamento
        raise RuntimeError("404 NOT_FOUND")
    _fake_genai(monkeypatch, beh)
    with pytest.raises(TimeoutError):
        analyst._llm("s", "p")


def test_answer_falls_back_to_local_writer_when_gemini_fails(monkeypatch, analyst):
    def beh(model):
        raise RuntimeError("503 UNAVAILABLE")
    _fake_genai(monkeypatch, beh)
    meta = {"home_team_name": "A", "away_team_name": "B", "home_score": 2, "away_score": 1, "match_id": 1,
            "data_level": "BOXSCORE", "data_source": "fdcouk"}
    import pandas as pd

    box = {"team_stats": pd.DataFrame([{"team_name": "A", "stat_key": "shots_total", "stat_label": "Finalizações", "value": 18},
                                       {"team_name": "B", "stat_key": "shots_total", "stat_label": "Finalizações", "value": 7}]),
           "timeline": pd.DataFrame(), "lineups": pd.DataFrame(), "player_stats": pd.DataFrame()}
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst as D

    monkeypatch.setattr(D, "_down_until", 0.0)
    monkeypatch.setattr(D, "_reach", {"t": 9e18, "ok": 1.0})            # rede "no ar": a falha vem do servidor
    res = analyst.answer("quantas finalizações?", "A", meta, boxscore=box, prefer_llm=True)
    assert res["engine_used"].startswith("REDATOR LOCAL") and res.get("llm_error")
    assert "18" in res["report_markdown"]
    # disjuntor: depois da falha, a próxima pergunta nem tenta a nuvem (resposta local instantânea)
    import time

    t0 = time.time()
    res2 = analyst.answer("quantas finalizações?", "A", meta, boxscore=box, prefer_llm=True)
    assert res2["engine_used"] == "LOCAL_SCOPED_ENGINE" and time.time() - t0 < 1.0


# ------------------------------------------------- motor neural (GroupKFold + promoção estatística)
@pytest.fixture()
def small_data():
    from src.machine_learning.model_registry import DangerModelRegistry

    d = DangerModelRegistry.dataset()
    return d[d["match_id"].isin(sorted(d["match_id"].unique())[:24])]


def test_group_kfold_never_mixes_matches(small_data, monkeypatch):
    from sklearn.model_selection import GroupKFold

    from src.machine_learning.model_registry import DangerModelRegistry

    seen = []
    orig = GroupKFold.split

    def spy(self, X, y=None, groups=None):
        for tr, va in orig(self, X, y, groups):
            seen.append((set(groups[tr]), set(groups[va])))
            yield tr, va
    monkeypatch.setattr(GroupKFold, "split", spy)
    cv = DangerModelRegistry.group_cv(small_data, [8], 0.05, 2, 1e-3, 256, folds=4, seeds=(1, 2))
    assert cv["folds"] == 4 and cv["seeds"] == 2 and len(cv["logloss"]) == 8
    assert seen and all(not (tr & va) for tr, va in seen)              # nenhuma partida dos dois lados


def test_clone_of_champion_is_rejected_and_every_attempt_is_logged(tmp_path, small_data):
    import json as _json

    from src.machine_learning.model_registry import DangerModelRegistry

    reg = DangerModelRegistry(root=tmp_path / "reg")
    r1 = reg.train_round(small_data, [8], 0.05, 3, 1e-3, 256, seed=5, cv_folds=3, cv_seeds=(1,))
    r2 = reg.train_round(small_data, [8], 0.05, 3, 1e-3, 256, seed=5, cv_folds=3, cv_seeds=(1,),
                         warm_start=False)                                                          # mesmo modelo
    assert r1["promoted"] and not r2["promoted"]
    assert abs(r2["test_gain"]) < 1e-9 and "IC 95% inclui zero" in r2["reason"]
    assert r2["cv_folds"] == 3 and r2["cv_logloss_std"] is not None
    lines = (tmp_path / "reg" / "tentativas.jsonl").read_text(encoding="utf-8").splitlines()
    assert [(_json.loads(l)["version"], _json.loads(l)["promoted"]) for l in lines] == [(1, True), (2, False)]
    assert reg.champion_info()["version"] == 1


def test_clear_improvement_is_promoted(tmp_path, small_data):
    from src.machine_learning.model_registry import DangerModelRegistry

    reg = DangerModelRegistry(root=tmp_path / "reg")
    reg.train_round(small_data, [4], 0.001, 1, 1e-3, 256, seed=3, cv_folds=0)          # campeão fraco (quase sem treino)
    r = reg.train_round(small_data, [16], 0.05, 20, 1e-3, 256, seed=3, cv_folds=3, cv_seeds=(1, 2))
    assert r["promoted"], r["reason"]
    assert r["gain_ci_low"] > 0 and r["test_gain"] >= 0.0005 and r["optimizer"] == "adam"
    assert reg.champion_info()["version"] == 2


# ------------------------------------------------------------- identidade visual
def test_theme_css_never_leaks_as_text_and_has_fm_identity():
    import re as _re

    pytest.importorskip("streamlit")
    from src.ui.theme import CSS, PALETTE

    css = CSS.strip()
    assert css.startswith("<style>") and css.endswith("</style>")
    assert not _re.search(r"\n[ \t]*\n", css)              # linha em branco encerra o bloco HTML → vazaria como texto
    assert "<link" not in css                               # fontes via @import dentro do <style>
    assert PALETTE["bg"].upper() == "#090D16"
    for token in ("#1E2A44", ".fm-card", ".fm-card-blue", ".fm-card-red", "Space Grotesk", "Inter"):
        assert token.lower() in css.lower(), token
    assert {PALETTE["accent"].upper(), PALETTE["primary"].upper()} == {"#22D3EE", "#3B82F6"}
    assert PALETTE["secondary"].upper() == "#EF4444"


def test_gemini_uses_models_released_for_the_key_first(monkeypatch, analyst, tmp_path):
    """Caso real do usuário: 2.5-flash 'no longer available to new users'; a chave libera 3.x-flash."""
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst as D

    monkeypatch.setattr(D, "_discovered", None)
    monkeypatch.setattr(D, "MODELS_CACHE", tmp_path / "modelos.json")
    released = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-flash-image", "gemini-2.5-flash",
                "gemini-2.5-flash-image", "gemini-omni-flash-preview"]

    def beh(model):
        if model.startswith("gemini-2"):
            raise RuntimeError("404 NOT_FOUND This model is no longer available to new users")
        return types.SimpleNamespace(text=f"resposta de {model}")
    calls = _fake_genai(monkeypatch, beh)
    import sys as _sys

    _sys.modules["google.genai"].Client.__init__.__globals__  # garante o módulo falso carregado
    monkeypatch.setattr(_sys.modules["google.genai"], "Client", _client_listing(_sys.modules["google.genai"].Client, released))
    assert analyst._llm("s", "p") == "resposta de gemini-3.8-flash"
    assert [c[0] for c in calls] == ["gemini-3.8-flash"]                   # primeira tentativa já certa
    assert (tmp_path / "modelos.json").exists()                            # lista guardada (sem a chave)
    assert "chave-falsa" not in (tmp_path / "modelos.json").read_text(encoding="utf-8")


def _client_listing(Base, names):
    class C(Base):
        def __init__(self, api_key, http_options=None):
            super().__init__(api_key, http_options)
            self.models.list = lambda: [types.SimpleNamespace(name=f"models/{n}", supported_actions=["generateContent"])
                                        for n in names]
    return C


def test_screen_text_has_no_tags_but_untraceable_still_cut():
    res = {"report_markdown": "Finalizações: **18** contra **7**. Ele deu 977 passes errados.", "evidence": EV}
    present(res)                                                           # padrão da tela: sem etiquetas
    t = res["report_markdown"]
    assert "[EXATO]" not in t and "[DERIVADO]" not in t and "977" not in t and "**18**" in t
    assert res["number_tags"]["ocultadas"] == 1
    assert {r["origem"] for r in res["number_tags"]["linhas"]} >= {"EXATO"}


def test_national_team_names_in_portuguese_on_screen_only():
    from src.ui.names import pt, pt_text

    assert pt("Brazil") == "Brasil" and pt("Croatia") == "Croácia" and pt("Brazil Women's") == "Brasil (fem.)"
    assert pt("Flamengo") == "Flamengo"
    assert pt_text("Plano de Argentina contra France; empurraram Argentina para o ataque. Portugal.",
                   ["Argentina", "France", "Portugal"]) == \
        "Plano da Argentina contra a França; empurraram Argentina para o ataque. Portugal."
    assert pt_text("Croatia entrou na área; a defesa de Brazil sofreu. Brazilian fans.", ["Croatia", "Brazil"]) == \
        "Croácia entrou na área; a defesa do Brasil sofreu. Brazilian fans."
    ev = {"metadata": {"target_team": "Brazil", "opponent_team": "Croatia"},
          "blocos": {"x": {"Finalizações": {"Brazil": 24, "Croatia": 9}}}}
    res = {"report_markdown": "Brazil finalizou 24 vezes contra 9 de Croatia.", "evidence": ev}
    present(res)
    assert res["report_markdown"].startswith("Brasil finalizou 24 vezes contra 9 da Croácia")
    assert res["report_raw"].startswith("Brazil")                          # o dado original fica intacto
