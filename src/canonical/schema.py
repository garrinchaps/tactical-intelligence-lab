"""
Schema canônico de eventos (Bloco 1).

Todo conector que entrega EVENTOS produz exatamente as colunas abaixo, com os tipos,
domínios e regras de nulo declarados em CANONICAL_EVENT_SCHEMA. Conectores que
entregam AGREGADOS (boxscore, arquivos de scout, estimativas por bootstrap) usam o
schema canônico de agregados, que compartilha o mesmo bloco de proveniência.

Bloco de proveniência (obrigatório em todo registro persistido):
    source, connector, license, ingestion_timestamp, confidence_tier

Tiers de confiança:
    OFFICIAL  — valor entregue diretamente por um provedor oficial (ex.: evento StatsBomb).
    DERIVED   — valor calculado/inferido pelo laboratório a partir de dados reais
                (ex.: PPDA, posição inferida, xG estimado) ou vindo de fonte não oficial.
    SIMULATED — valor produzido por gerador probabilístico (inclui IC 95% da reamostragem).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

EVENT_TYPES = ("passe", "condução", "finalização", "pressão", "recuperação", "drible", "falta", "outro")
EVENT_OUTCOMES = ("sucesso", "falha", "nulo")
CONFIDENCE_TIERS = ("OFFICIAL", "DERIVED", "SIMULATED")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: str                    # "str" | "int" | "float"
    nullable: bool
    domain: str                   # descrição legível do domínio
    check: Optional[Callable[[pd.Series], pd.Series]] = None  # devolve máscara de valores VÁLIDOS
    null_rule: str = ""


def _iso(s: pd.Series) -> pd.Series:
    def ok(v: Any) -> bool:
        try:
            datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return s.map(ok)


PROVENANCE_FIELDS: Tuple[FieldSpec, ...] = (
    FieldSpec("source", "str", False, "nome da fonte (ex.: 'StatsBomb Open Data')",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo"),
    FieldSpec("connector", "str", False, "classe que ingeriu o dado (ex.: 'StatsBombConnector')",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo"),
    FieldSpec("license", "str", False, "licença/termo de uso da fonte",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo"),
    FieldSpec("ingestion_timestamp", "str", False, "ISO 8601 em UTC", _iso, "proibido nulo"),
    FieldSpec("confidence_tier", "str", False, "OFFICIAL | DERIVED | SIMULATED",
              lambda s: s.isin(CONFIDENCE_TIERS), "proibido nulo"),
)

CANONICAL_EVENT_SCHEMA: Tuple[FieldSpec, ...] = (
    FieldSpec("match_id", "str", False, "identificador interno da partida (texto)",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo"),
    FieldSpec("team_id", "str", False, "identificador da equipe que executa o evento",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo; usa o nome da equipe se a fonte não tiver ID"),
    FieldSpec("player_id", "str", True, "identificador do atleta",
              None, "nulo permitido em eventos de equipe (ex.: troca tática)"),
    FieldSpec("event_type", "str", False, " | ".join(EVENT_TYPES),
              lambda s: s.isin(EVENT_TYPES), "proibido nulo; tipos sem correspondência viram 'outro'"),
    FieldSpec("minute", "int", False, "0 a 130", lambda s: s.between(0, 130), "proibido nulo"),
    FieldSpec("second", "int", False, "0 a 59", lambda s: s.between(0, 59), "proibido nulo"),
    FieldSpec("x", "float", False, "0 a 120 (comprimento, coordenadas StatsBomb)",
              lambda s: s.between(0.0, 120.0), "eventos sem localização são excluídos da tabela canônica"),
    FieldSpec("y", "float", False, "0 a 80 (largura, coordenadas StatsBomb)",
              lambda s: s.between(0.0, 80.0), "eventos sem localização são excluídos da tabela canônica"),
    FieldSpec("event_outcome", "str", False, " | ".join(EVENT_OUTCOMES),
              lambda s: s.isin(EVENT_OUTCOMES), "proibido nulo; 'nulo' quando o tipo não tem desfecho"),
    FieldSpec("score_state", "str", False, "'casa-fora' antes do evento (ex.: '1-0')",
              lambda s: s.astype(str).str.fullmatch(r"\d{1,2}-\d{1,2}"), "proibido nulo"),
) + PROVENANCE_FIELDS

CANONICAL_AGGREGATE_SCHEMA: Tuple[FieldSpec, ...] = (
    FieldSpec("match_id", "str", True, "partida (nulo quando o agregado é de temporada/estrato)", None,
              "nulo permitido"),
    FieldSpec("team_id", "str", True, "equipe", None, "nulo permitido em agregados de referência"),
    FieldSpec("entity", "str", False, "objeto medido (equipe, atleta, zona, par passador→receptor, estrato)",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo"),
    FieldSpec("metric", "str", False, "nome da métrica (ex.: 'xt_zona', 'passes_par', 'ppda')",
              lambda s: s.astype(str).str.len() > 0, "proibido nulo"),
    FieldSpec("value", "float", False, "valor numérico finito", lambda s: np.isfinite(s.astype(float)),
              "proibido nulo"),
    FieldSpec("ci_low", "float", True, "limite inferior do IC 95% (só SIMULATED)", None, "nulo fora do tier SIMULATED"),
    FieldSpec("ci_high", "float", True, "limite superior do IC 95% (só SIMULATED)", None, "nulo fora do tier SIMULATED"),
) + PROVENANCE_FIELDS

EVENT_COLUMNS = [f.name for f in CANONICAL_EVENT_SCHEMA]
AGGREGATE_COLUMNS = [f.name for f in CANONICAL_AGGREGATE_SCHEMA]
PANDAS_DTYPES = {"str": "object", "int": "int64", "float": "float64"}


class SchemaViolation(ValueError):
    """Dados fora do schema canônico; a mensagem cita coluna, regra e exemplos."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate(df: pd.DataFrame, schema: Tuple[FieldSpec, ...] = CANONICAL_EVENT_SCHEMA,
             raise_on_error: bool = True) -> List[str]:
    """Confere nomes e ordem das colunas, tipos, nulos e domínios. Devolve a lista de problemas."""
    problems: List[str] = []
    expected = [f.name for f in schema]
    if list(df.columns) != expected:
        missing = [c for c in expected if c not in df.columns]
        extra = [c for c in df.columns if c not in expected]
        problems.append(f"colunas diferentes do schema (faltando: {missing}; sobrando: {extra})")
    for f in schema:
        if f.name not in df.columns:
            continue
        col = df[f.name]
        if not f.nullable and col.isna().any():
            problems.append(f"'{f.name}': {int(col.isna().sum())} valores nulos (regra: {f.null_rule})")
        present = col.dropna()
        if f.dtype == "int" and not pd.api.types.is_integer_dtype(col):
            problems.append(f"'{f.name}': tipo {col.dtype}, esperado inteiro")
        if f.dtype == "float" and not pd.api.types.is_float_dtype(col):
            problems.append(f"'{f.name}': tipo {col.dtype}, esperado float")
        if f.dtype == "str" and len(present) and not present.map(lambda v: isinstance(v, str)).all():
            problems.append(f"'{f.name}': há valores que não são texto")
        if f.check is not None and len(present):
            ok = f.check(present)
            if not ok.all():
                bad = present[~ok].head(3).tolist()
                problems.append(f"'{f.name}': {int((~ok).sum())} valores fora do domínio [{f.domain}], ex.: {bad}")
    if problems and raise_on_error:
        raise SchemaViolation("; ".join(problems))
    return problems


def schema_table(schema: Tuple[FieldSpec, ...] = CANONICAL_EVENT_SCHEMA) -> pd.DataFrame:
    """Tabela legível do schema (para documentação e para a página de Catálogo)."""
    return pd.DataFrame([{"campo": f.name, "tipo": f.dtype, "nulo": "sim" if f.nullable else "não",
                          "domínio": f.domain, "tratamento de nulo": f.null_rule} for f in schema])


# --------------------------------------------------------------- conversão
_TYPE_MAP = {
    "Pass": "passe", "Carry": "condução", "Shot": "finalização", "Pressure": "pressão",
    "Ball Recovery": "recuperação", "Interception": "recuperação", "Dribble": "drible",
    "Foul Committed": "falta",
}
_SUCCESS = {"Complete", "Won", "Success", "Success In Play", "Success Out", "Goal"}


def _outcome(row: pd.Series) -> str:
    t = row.get("type_name")
    if t == "Pass":
        return "falha" if isinstance(row.get("pass_outcome_name"), str) and row.get("pass_outcome_name") else "sucesso"
    if t == "Shot":
        return "sucesso" if row.get("shot_outcome_name") == "Goal" else "falha"
    if t in ("Dribble",):
        return "sucesso" if row.get("duel_outcome_name") in _SUCCESS or row.get("dribble_outcome_name") in _SUCCESS else "falha"
    if t == "Interception":
        out = row.get("interception_outcome_name")
        return "falha" if isinstance(out, str) and out.startswith("Lost") else "sucesso"
    if t == "Ball Recovery":
        return "falha" if row.get("ball_recovery_recovery_failure") in (True, 1) else "sucesso"
    if t == "Duel":
        out = row.get("duel_outcome_name")
        return "sucesso" if out in _SUCCESS else ("falha" if isinstance(out, str) and out else "nulo")
    return "nulo"


def _score_states(df: pd.DataFrame, home: str) -> pd.Series:
    """Placar 'casa-fora' ANTES de cada evento (gols e gols contra; disputa de pênaltis fora)."""
    h = a = 0
    out = []
    for r in df.itertuples(index=False):
        out.append(f"{h}-{a}")
        if getattr(r, "period", 1) > 4:
            continue
        t = getattr(r, "type_name", "")
        team = getattr(r, "team_name", "")
        if t == "Shot" and getattr(r, "shot_outcome_name", None) == "Goal":
            if team == home:
                h += 1
            else:
                a += 1
        elif t == "Own Goal Against":
            if team == home:
                a += 1
            else:
                h += 1
    return pd.Series(out, index=df.index)


def to_canonical_events(
    df_internal: pd.DataFrame,
    source: str,
    connector: str,
    license: str,
    confidence_tier: str,
    home_team: Optional[str] = None,
    ingestion_timestamp: Optional[str] = None,
) -> pd.DataFrame:
    """Converte o DataFrame interno de eventos (padrão do pipeline) para o schema canônico."""
    if confidence_tier not in CONFIDENCE_TIERS:
        raise SchemaViolation(f"confidence_tier inválido: {confidence_tier}")
    if df_internal is None or df_internal.empty:
        return pd.DataFrame({c: pd.Series(dtype=PANDAS_DTYPES[f.dtype]) for c, f in
                             zip(EVENT_COLUMNS, CANONICAL_EVENT_SCHEMA)})
    d = df_internal.copy()
    order = [c for c in ("period", "index_num") if c in d.columns]
    if order:
        d = d.sort_values(order, kind="stable")
    home = home_team or str(d["team_name"].dropna().iloc[0])
    d["__score"] = _score_states(d, home)
    d = d[d["x"].notna() & d["y"].notna() & (d.get("period", 1) <= 4)].copy()
    team_id = d["team_id"] if "team_id" in d.columns else pd.Series(np.nan, index=d.index)
    player_id = d["player_id"] if "player_id" in d.columns else pd.Series(np.nan, index=d.index)
    out = pd.DataFrame({
        "match_id": d["match_id"].astype("int64").astype(str),
        "team_id": [str(int(t)) if pd.notna(t) and str(t).replace(".0", "").isdigit() and int(float(t)) != 0
                    else str(n) for t, n in zip(team_id, d["team_name"])],
        "player_id": [str(int(p)) if pd.notna(p) and str(p).replace(".0", "").isdigit() else None for p in player_id],
        "event_type": d["type_name"].map(_TYPE_MAP).fillna("outro"),
        "minute": d["minute"].fillna(0).astype("int64").clip(0, 130),
        "second": d["second"].fillna(0).astype("int64").clip(0, 59),
        "x": d["x"].astype(float).clip(0.0, 120.0),
        "y": d["y"].astype(float).clip(0.0, 80.0),
        "event_outcome": d.apply(_outcome, axis=1),
        "score_state": d["__score"],
        "source": source,
        "connector": connector,
        "license": license,
        "ingestion_timestamp": ingestion_timestamp or utc_now_iso(),
        "confidence_tier": confidence_tier,
    })
    out["player_id"] = out["player_id"].astype(object)
    return out.reset_index(drop=True)[EVENT_COLUMNS]


def make_aggregate_frame(rows: List[Dict[str, Any]], source: str, connector: str, license: str,
                         confidence_tier: str, ingestion_timestamp: Optional[str] = None) -> pd.DataFrame:
    """Monta e valida um DataFrame no schema canônico de agregados."""
    ts = ingestion_timestamp or utc_now_iso()
    recs = []
    for r in rows:
        recs.append({
            "match_id": None if r.get("match_id") in (None, "") else str(r["match_id"]),
            "team_id": None if r.get("team_id") in (None, "") else str(r["team_id"]),
            "entity": str(r["entity"]), "metric": str(r["metric"]), "value": float(r["value"]),
            "ci_low": None if r.get("ci_low") is None else float(r["ci_low"]),
            "ci_high": None if r.get("ci_high") is None else float(r["ci_high"]),
            "source": source, "connector": connector, "license": license,
            "ingestion_timestamp": ts, "confidence_tier": confidence_tier,
        })
    df = pd.DataFrame(recs, columns=AGGREGATE_COLUMNS)
    for c in ("value", "ci_low", "ci_high"):
        df[c] = df[c].astype(float)
    for c in ("match_id", "team_id"):
        df[c] = df[c].astype(object)
    validate(df, CANONICAL_AGGREGATE_SCHEMA)
    return df
