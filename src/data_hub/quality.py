"""
Qualidade de dados: validação de domínio e detecção de duplicatas por SHA-256 do conteúdo normalizado.

Regras de domínio
  * placar: inteiro ≥ 0 (vazio só em jogo não encerrado);
  * equipes: presentes e diferentes entre si;
  * data: AAAA-MM-DD válida, não no futuro para jogo encerrado, e coerente com a temporada
    ("2023/24" ou "2023/2024" → 01/06/2023 a 31/07/2024; "2024" → 01/01/2024 a 31/07/2025);
  * minuto de evento/lance: 0 a 130;
  * coordenadas (escala StatsBomb): x em 0–120 e y em 0–80 (início e fim).

`validate_matches` separa linhas válidas e rejeitadas (com o motivo); `upsert_matches` usa isso para
nunca gravar placar negativo, equipe vazia ou data impossível. Avisos (ex.: data fora da temporada) não
bloqueiam: aparecem no relatório de qualidade.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

MINUTE_MAX = 130
X_MAX, Y_MAX = 120.0, 80.0
FINISHED = {"FT", "AET", "PEN", "", None}


# ------------------------------------------------------------------- partidas
def _int_or_none(v: Any) -> Tuple[bool, Optional[int]]:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return True, None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False, None
    if f != int(f):
        return False, None
    return True, int(f)


def season_window(season: Any) -> Optional[Tuple[date, date]]:
    s = str(season or "").strip()
    m = re.match(r"^(\d{4})\s*[/\-]\s*(\d{2}|\d{4})$", s)
    if m:
        y1 = int(m.group(1))
        return date(y1, 6, 1), date(y1 + 1, 7, 31)
    m = re.match(r"^(\d{4})$", s)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y + 1, 7, 31)   # torneios adiados (ex.: Euro 2020 em jul/2021)
    return None


def check_match(r: Dict[str, Any], today: Optional[date] = None) -> Tuple[List[str], List[str]]:
    """(erros que bloqueiam, avisos)."""
    today = today or date.today()
    errors, warns = [], []
    h, a = str(r.get("home_team_name") or "").strip(), str(r.get("away_team_name") or "").strip()
    if not h or not a:
        errors.append("equipe ausente")
    elif h.lower() == a.lower():
        errors.append("mandante igual ao visitante")
    for side in ("home_score", "away_score"):
        ok, v = _int_or_none(r.get(side))
        if not ok:
            errors.append(f"{side} não é inteiro")
        elif v is not None and v < 0:
            errors.append(f"{side} negativo")
    d = str(r.get("match_date") or "")[:10]
    if d:
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"data inválida ({d})")
            dd = None
        if dd is not None:
            if dd.year < 1870:
                errors.append(f"data anterior a 1870 ({d})")
            if dd > today and r.get("status") in ("FT", "AET", "PEN") and r.get("home_score") is not None:
                errors.append(f"jogo encerrado com data futura ({d})")
            w = season_window(r.get("season_name"))
            if w and not (w[0] <= dd <= w[1]):
                warns.append(f"data {d} fora da temporada {r.get('season_name')}")
    return errors, warns


def validate_matches(records: Iterable[Dict[str, Any]], today: Optional[date] = None
                     ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(válidas, rejeitadas com motivo, avisos)."""
    ok, bad, warn = [], [], []
    for r in records:
        e, w = check_match(r, today)
        if e:
            bad.append({"match_id": r.get("match_id"), "fonte": r.get("data_source"), "motivo": "; ".join(e)})
        else:
            ok.append(r)
        if w:
            warn.append({"match_id": r.get("match_id"), "fonte": r.get("data_source"), "aviso": "; ".join(w)})
    return ok, bad, warn


# -------------------------------------------------------------------- eventos
def validate_events(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas com minuto fora de 0–130 ou coordenada fora do campo (colunas `problema`)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["index", "problema"])
    probs = pd.Series("", index=df.index)

    def flag(mask, txt):
        nonlocal probs
        mask = mask.fillna(False)
        probs = probs.where(~mask, probs + (txt + "; "))
    if "minute" in df:
        m = pd.to_numeric(df["minute"], errors="coerce")
        flag((m < 0) | (m > MINUTE_MAX), f"minuto fora de 0–{MINUTE_MAX}")
    for cx, cy in (("x", "y"), ("location_x", "location_y"), ("end_x", "end_y"), ("pass_end_x", "pass_end_y")):
        if cx in df:
            x = pd.to_numeric(df[cx], errors="coerce")
            flag((x < 0) | (x > X_MAX), f"{cx} fora de 0–{X_MAX:g}")
        if cy in df:
            y = pd.to_numeric(df[cy], errors="coerce")
            flag((y < 0) | (y > Y_MAX), f"{cy} fora de 0–{Y_MAX:g}")
    out = probs[probs != ""]
    return pd.DataFrame({"index": out.index, "problema": out.str.rstrip("; ").values})


def clean_timeline(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Descarta lances com minuto impossível (mantém os sem minuto)."""
    out = []
    for e in items or []:
        m = e.get("minute")
        if m is not None and not (isinstance(m, float) and pd.isna(m)):
            try:
                if not (0 <= float(m) <= MINUTE_MAX):
                    continue
            except (TypeError, ValueError):
                continue
        out.append(e)
    return out


# ------------------------------------------------------------------ duplicatas
def content_hash(r: Dict[str, Any]) -> str:
    """SHA-256 do conteúdo normalizado: data, equipes (núcleo do nome), placar e competição."""
    from src.data_lake.ids import norm, team_core

    payload = {
        "d": str(r.get("match_date") or "")[:10],
        "h": team_core(r.get("home_team_name")),
        "a": team_core(r.get("away_team_name")),
        "hs": _int_or_none(r.get("home_score"))[1],
        "as": _int_or_none(r.get("away_score"))[1],
        "c": norm(r.get("competition_name")),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def find_duplicates(catalog: pd.DataFrame) -> pd.DataFrame:
    """
    Partidas com o mesmo conteúdo. `tipo`:
      * duplicata — mesmo conteúdo, mesma fonte, ids diferentes (erro a corrigir);
      * mesma partida em outra fonte — esperado (é a ligação entre bases).
    """
    if catalog is None or catalog.empty:
        return pd.DataFrame(columns=["hash", "match_id", "data_source", "tipo"])
    c = catalog.copy()
    c["hash"] = [content_hash(r) for r in c.to_dict("records")]
    multi = c[c.duplicated("hash", keep=False)]
    if multi.empty:
        return pd.DataFrame(columns=["hash", "match_id", "data_source", "tipo"])
    same_src = multi.duplicated(["hash", "data_source"], keep=False)
    multi = multi.assign(tipo=["duplicata" if s else "mesma partida em outra fonte" for s in same_src])
    cols = [x for x in ["hash", "match_id", "data_source", "match_date", "home_team_name", "away_team_name",
                        "home_score", "away_score", "competition_name", "tipo"] if x in multi]
    return multi[cols].sort_values(["hash", "data_source"]).reset_index(drop=True)


def audit(db) -> Dict[str, Any]:
    """Relatório de qualidade sobre o banco inteiro (usado em docs/COBERTURA.md)."""
    cat = db.catalog()
    cat = cat[~cat["data_level"].isin(["SIMULATED", "UPLOAD"])] if "data_level" in cat else cat
    _, bad, warn = validate_matches(cat.to_dict("records"))
    dups = find_duplicates(cat)
    with db.connect() as conn:
        tl_bad = conn.execute(f"SELECT COUNT(*) FROM match_timeline WHERE minute < 0 OR minute > {MINUTE_MAX}").fetchone()[0]
        ev_bad = 0
        cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
        conds = [f"minute < 0 OR minute > {MINUTE_MAX}"] if "minute" in cols else []
        for cx, lim in (("x", X_MAX), ("y", Y_MAX), ("end_x", X_MAX), ("end_y", Y_MAX)):
            if cx in cols:
                conds.append(f"{cx} < 0 OR {cx} > {lim}")
        if conds:
            ev_bad = conn.execute("SELECT COUNT(*) FROM events WHERE " + " OR ".join(f"({c})" for c in conds)).fetchone()[0]
    return {"partidas": len(cat), "rejeitaveis": pd.DataFrame(bad), "avisos": pd.DataFrame(warn),
            "duplicatas": dups[dups["tipo"] == "duplicata"] if not dups.empty else dups,
            "ligacoes": int((dups["tipo"] != "duplicata").sum()) if not dups.empty else 0,
            "lances_fora": int(tl_bad), "eventos_fora": int(ev_bad)}
