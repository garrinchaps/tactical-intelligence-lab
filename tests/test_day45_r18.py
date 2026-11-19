"""Rodada 18: função tática vetorizada (sem travar na base grande) e porta da versão pública."""
import time

import numpy as np
import pandas as pd

from src.scout import evaluation as EV
from src.ui import gate


def _pool(n, seed=3):
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"family": rng.choice(list(EV.WEIGHTS) + [None], n),
                      "comp": rng.choice([f"liga {i}" for i in range(40)], n)})
    for c in EV.FUNC_COLS:
        d[c] = np.where(rng.random(n) < .2, np.nan, rng.random(n))
    return d


def test_vectorized_function_matches_row_by_row():
    d = _pool(3000)
    pre = pd.DataFrame({c: EV._strict_pct(d, c) for c in EV.FUNC_COLS}, index=d.index)
    recs = pre.to_dict("records")
    fast = [EV._classify(f, (lambda c, r=r: None if pd.isna(r.get(c)) else float(r[c]))) for f, r in zip(d["family"], recs)]
    for i in d.sample(150, random_state=1).index:
        assert EV._function(d.loc[i], d) == fast[d.index.get_loc(i)]


def test_strict_pct_needs_eight_peers():
    d = pd.DataFrame({"family": ["ST"] * 7 + ["CB"] * 9, "comp": ["x"] * 16, "goals_p90": list(range(7)) + list(range(9))})
    p = EV._strict_pct(d, "goals_p90")
    assert p[:7].isna().all()                                    # 7 atacantes: poucos para comparar
    assert p.iloc[7] == 0 and round(p.iloc[15], 1) == round(8 / 9 * 100, 1)


def test_function_classification_is_fast_on_big_pool():
    d = _pool(40000)
    t = time.time()
    pre = pd.DataFrame({c: EV._strict_pct(d, c) for c in EV.FUNC_COLS}, index=d.index)
    recs = pre.to_dict("records")
    [EV._classify(f, (lambda c, r=r: None if pd.isna(r.get(c)) else float(r[c]))) for f, r in zip(d["family"], recs)]
    assert time.time() - t < 15                                  # antes: horas (cada jogador × todos os colegas)


def test_gate_visitor_detection(monkeypatch):
    monkeypatch.delenv("TIL_MODO_PUBLICO", raising=False)
    assert not gate.is_visitor({"Host": "localhost:8501"})
    assert not gate.is_visitor({"Host": "127.0.0.1:8501"})
    assert gate.is_visitor({"Host": "abc-def.trycloudflare.com"})
    assert gate.is_visitor({"Host": "localhost:8501", "Cf-Connecting-Ip": "1.2.3.4"})   # túnel com Host local
    monkeypatch.setenv("TIL_MODO_PUBLICO", "1")
    assert gate.is_visitor({"Host": "localhost:8501"})


def test_gate_password_check():
    assert gate.check("abc", expected="abc")
    assert not gate.check("abd", expected="abc")
    assert not gate.check("", expected="")                      # sem senha configurada nunca "acerta"


def test_public_mode_turns_off_autosync(monkeypatch):
    from src.data_hub import autosync

    monkeypatch.setenv("TIL_MODO_PUBLICO", "1")
    assert not autosync.enabled()


def test_presentation_checklist_runs_offline(monkeypatch, tmp_path):
    from src.tools import apresentacao

    monkeypatch.setenv("TACTICAL_DB_PATH", str(tmp_path / "nao_existe.db"))     # nunca abre o banco real no teste
    rows = apresentacao.checks(port=59999)
    assert rows and all(len(r) == 3 for r in rows)
    assert any("cloudflared" in r[1] for r in rows)
    assert any(r[1] == "Banco de dados" and r[0] == apresentacao.BAD for r in rows)
    assert not (tmp_path / "nao_existe.db").exists()
