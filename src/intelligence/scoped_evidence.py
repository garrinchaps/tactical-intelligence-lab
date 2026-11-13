"""
Evidências recortadas sob medida para a pergunta (QueryScope).

Em vez de despejar todas as métricas da partida, calcula somente os blocos que a
pergunta pede, dentro do recorte (janela de minutos, tempo, lado, terço, atleta) e,
quando há recorte de tempo, compara com o resto do jogo.

Convenção espacial (coordenadas StatsBomb, cada equipe atacando da esquerda p/ direita):
* lado esquerdo da equipe = y < 30, centro = 30–50, direito = y > 50;
* eventos do adversário são espelhados (x → 120 − x, y → 80 − y) para ficarem no
  referencial da equipe analisada (ex.: ataque adversário pela direita dele = nosso lado esquerdo).
Sem tracking, "compactação" é estimada pela dispersão das ações defensivas (proxy declarada).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.intelligence.query_understanding import QueryScope

YD_TO_M = 0.9144
SIDES = {"left": (-5.0, 30.0), "center": (30.0, 50.0), "right": (50.0, 85.0)}
THIRDS = {"defensive": (-5.0, 40.0), "middle": (40.0, 80.0), "attacking": (80.0, 125.0)}
SIDE_PT = {"left": "lado esquerdo", "right": "lado direito", "center": "corredor central"}


def _r(v: Any, nd: int = 2) -> Any:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), nd)


def _pct(a: float, b: float) -> Optional[float]:
    return round(100.0 * a / b, 1) if b else None


class ScopedEvidenceBuilder:
    # ----------------------------------------------------------- filtros
    @staticmethod
    def _time_mask(df: pd.DataFrame, sc: QueryScope) -> pd.Series:
        m = df["period"] <= 4  # disputa de pênaltis (período 5) não entra na análise tática
        if sc.period:
            m &= df["period"] == sc.period
        if sc.minute_from is not None:
            m &= (df["minute"] >= sc.minute_from) & (df["minute"] <= (sc.minute_to or 130))
        return m

    @staticmethod
    def _own_frame(df: pd.DataFrame, team: str) -> pd.DataFrame:
        """Coordenadas no referencial de `team` (adversário espelhado)."""
        out = df.copy()
        opp = out["team_name"] != team
        for c, size in (("x", 120.0), ("end_x", 120.0)):
            out.loc[opp, c] = size - out.loc[opp, c]
        for c, size in (("y", 80.0), ("end_y", 80.0)):
            out.loc[opp, c] = size - out.loc[opp, c]
        return out

    @staticmethod
    def _zone_mask(df: pd.DataFrame, sc: QueryScope, use_end: bool = False) -> pd.Series:
        xc, yc = ("end_x", "end_y") if use_end else ("x", "y")
        m = pd.Series(True, index=df.index)
        if sc.side:
            lo, hi = SIDES[sc.side]
            m &= (df[yc] >= lo) & (df[yc] < hi)
        if sc.third:
            lo, hi = THIRDS[sc.third]
            m &= (df[xc] >= lo) & (df[xc] < hi)
        return m

    # ------------------------------------------------------------ blocos
    @classmethod
    def block_context(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        w = df[cls._time_mask(df, sc)]
        goals = w[(w["type_name"] == "Shot") & (w.get("shot_outcome_name") == "Goal")]
        own_goals = w[w["type_name"].isin(["Own Goal Against"])]
        passes = w[w["type_name"] == "Pass"]
        team_passes = int((passes["team_name"] == team).sum())
        return {
            "recorte": sc.describe(),
            "eventos_no_recorte": int(len(w)),
            "gols_no_recorte": [
                {"minuto": int(r.minute), "equipe": r.team_name, "jogador": r.player_name}
                for r in goals.itertuples()
            ] + [{"minuto": int(r.minute), "equipe": opp if r.team_name == team else team, "jogador": f"gol contra de {r.player_name}"}
                 for r in own_goals.itertuples()],
            "share_de_passes_pct": {team: _pct(team_passes, len(passes)), opp: _pct(len(passes) - team_passes, len(passes))},
        }

    @classmethod
    def block_defense(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        f = cls._own_frame(df, team)
        tm = cls._time_mask(f, sc)
        zone_end = cls._zone_mask(f, sc, use_end=True)
        zone_start = cls._zone_mask(f, sc)
        opp_ev = f[(f["team_name"] == opp) & tm]
        team_ev = f[(f["team_name"] == team) & tm]

        # ataques adversários que chegam ao setor (fim da ação no setor; padrão: nossa metade)
        if not sc.third:
            zone_end &= f["end_x"] < 60.0
            zone_start &= f["x"] < 60.0
        moves = opp_ev[opp_ev["type_name"].isin(["Pass", "Carry"]) & zone_end.loc[opp_ev.index]]
        completed = moves[(moves["type_name"] == "Carry") | (moves["is_pass_completed"] == 1)]
        prog = completed[completed.get("is_progressive_action", 0) == 1]
        box_from_side = opp_ev[(opp_ev.get("is_box_entry", 0) == 1)]
        if sc.side:
            lo, hi = SIDES[sc.side]
            box_from_side = box_from_side[(box_from_side["y"] >= lo) & (box_from_side["y"] < hi)]
        shots = opp_ev[(opp_ev["type_name"] == "Shot") & zone_start.loc[opp_ev.index]] if sc.side else \
            opp_ev[opp_ev["type_name"] == "Shot"]

        defa = team_ev[(team_ev["is_defensive_action"] == 1)]
        defa_zone = defa[zone_start.loc[defa.index]]
        duels = defa_zone[defa_zone["type_name"] == "Duel"]
        duels_won = duels[duels.get("duel_outcome_name").isin(["Won", "Success", "Success In Play", "Success Out"])]

        disp = defa.dropna(subset=["x", "y"])
        compact = {
            "acoes_defensivas_consideradas": int(len(disp)),
            "altura_media_m": _r(disp["x"].mean() * YD_TO_M, 1) if len(disp) else None,
            "dispersao_longitudinal_m": _r(disp["x"].std() * YD_TO_M, 1) if len(disp) > 2 else None,
            "dispersao_lateral_m": _r(disp["y"].std() * YD_TO_M, 1) if len(disp) > 2 else None,
            "nota": "proxy sem tracking: dispersão das ações defensivas, não a distância real entre linhas",
        }
        block = {
            "setor": (SIDE_PT.get(sc.side, "todo o campo") + (f" / {sc.third}" if sc.third else " (nossa metade)")),
            "acoes_adversarias_que_chegaram_ao_setor": int(len(moves)),
            "acoes_adversarias_completas_no_setor": int(len(completed)),
            "progressoes_adversarias_no_setor": int(len(prog)),
            "entradas_na_area_vindas_do_setor": int(len(box_from_side)),
            "finalizacoes_cedidas": int(len(shots)),
            "xg_cedido": _r(shots["shot_statsbomb_xg"].sum(), 2),
            "nossas_acoes_defensivas_no_setor": int(len(defa_zone)),
            "duelos_no_setor": int(len(duels)),
            "duelos_ganhos_no_setor_pct": _pct(len(duels_won), len(duels)),
            "faltas_no_setor": int((defa_zone["type_name"] == "Foul Committed").sum()),
            "compactacao_estimada": compact,
            "amostra_N": int(len(moves) + len(defa_zone)),
        }
        if sc.minute_from is not None or sc.period:
            rest_sc = QueryScope(raw="", side=sc.side, third=sc.third)
            rest = f[~tm]
            r_moves = rest[(rest["team_name"] == opp) & rest["type_name"].isin(["Pass", "Carry"]) &
                           cls._zone_mask(rest, rest_sc, use_end=True) & (rest["end_x"] < (125 if sc.third else 60))]
            minutes_in = max((sc.minute_to or 95) - (sc.minute_from or 0), 1) if sc.minute_from is not None else 45
            minutes_rest = max(95 - minutes_in, 1)
            r_def = rest[(rest["team_name"] == team) & (rest["is_defensive_action"] == 1)].dropna(subset=["x", "y"])
            block["comparacao_resto_do_jogo"] = {
                "acoes_adversarias_no_setor_por_10min_recorte": _r(10 * len(moves) / minutes_in, 1),
                "acoes_adversarias_no_setor_por_10min_resto": _r(10 * len(r_moves) / minutes_rest, 1),
                "dispersao_lateral_m_resto": _r(r_def["y"].std() * YD_TO_M, 1) if len(r_def) > 2 else None,
                "altura_media_m_resto": _r(r_def["x"].mean() * YD_TO_M, 1) if len(r_def) else None,
            }
        return block

    @classmethod
    def block_attack(cls, df: pd.DataFrame, sc: QueryScope, team: str) -> Dict[str, Any]:
        tm = cls._time_mask(df, sc)
        ev = df[(df["team_name"] == team) & tm]
        zone = cls._zone_mask(ev, sc)
        passes = ev[(ev["type_name"] == "Pass") & zone]
        comp = passes[passes["is_pass_completed"] == 1]
        shots = ev[(ev["type_name"] == "Shot") & zone]
        actors = ev[zone & ev["player_name"].notna()].groupby("player_name").size().sort_values(ascending=False)
        xt = comp["delta_xt"].clip(lower=0).sum() if "delta_xt" in comp else None
        return {
            "setor": SIDE_PT.get(sc.side, "todo o campo") + (f" / {sc.third}" if sc.third else ""),
            "passes_no_setor": int(len(passes)),
            "precisao_passes_no_setor_pct": _pct(len(comp), len(passes)),
            "acoes_progressivas": int((ev[zone].get("is_progressive_action", pd.Series(dtype=int)) == 1).sum()),
            "passes_que_quebram_linhas": int((comp.get("is_line_breaking_pass", pd.Series(dtype=int)) == 1).sum()),
            "entradas_na_area": int((ev[zone].get("is_box_entry", pd.Series(dtype=int)) == 1).sum()),
            "cruzamentos": int((passes.get("is_pass_cross", pd.Series(dtype=int)) == 1).sum()),
            "finalizacoes": int(len(shots)),
            "xg": _r(shots["shot_statsbomb_xg"].sum(), 2),
            "gols": int((shots.get("shot_outcome_name") == "Goal").sum()),
            "xt_gerado": _r(xt, 3),
            "protagonistas_no_setor": [{"jogador": k, "acoes": int(v)} for k, v in actors.head(3).items()],
            "amostra_N": int(len(passes) + len(shots)),
        }

    @classmethod
    def block_pressing(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        tm = cls._time_mask(df, sc)
        opp_passes = df[(df["team_name"] == opp) & tm & (df["type_name"] == "Pass") & (df["x"] <= 72)]
        acts = df[(df["team_name"] == team) & tm & df["type_name"].isin(
            ["Duel", "Interception", "Foul Committed", "Block", "Pressure"]) & (df["x"] >= 48)]
        rec_high = df[(df["team_name"] == team) & tm & (df["is_ball_recovery"] == 1) & (df["x"] >= 60)]
        has_pressure = bool((df["type_name"] == "Pressure").any())
        return {
            "ppda": _r(len(opp_passes) / max(len(acts), 1), 2),
            "passes_adversarios_na_construcao": int(len(opp_passes)),
            "acoes_defensivas_altas": int(len(acts)),
            "recuperacoes_no_campo_adversario": int(len(rec_high)),
            "fonte_tem_eventos_de_pressao": has_pressure,
            "amostra_N": int(len(opp_passes) + len(acts)),
        }

    @classmethod
    def block_transition(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        d = df.sort_values(["period", "time_seconds"]) if "time_seconds" in df else df
        tm = cls._time_mask(d, sc)
        losses = d[(d["team_name"] == team) & tm & (d["is_turnover"] == 1)]
        if sc.side:
            losses = losses[cls._zone_mask(losses, QueryScope(raw="", side=sc.side))]
        shots_after, recov_5s = 0, 0
        for r in losses.itertuples():
            nxt = d[(d["period"] == r.period) & (d["time_seconds"] > r.time_seconds) &
                    (d["time_seconds"] <= r.time_seconds + 15)]
            if ((nxt["team_name"] == opp) & (nxt["type_name"] == "Shot")).any():
                shots_after += 1
            n5 = nxt[nxt["time_seconds"] <= r.time_seconds + 5]
            if ((n5["team_name"] == team) & (n5["is_ball_recovery"] == 1)).any():
                recov_5s += 1
        return {
            "perdas_de_posse": int(len(losses)),
            "perdas_no_terco_defensivo": int((losses["x"] < 40).sum()),
            "finalizacoes_adversarias_em_ate_15s_apos_perda": int(shots_after),
            "recuperacoes_em_ate_5s_apos_perda": int(recov_5s),
            "taxa_recuperacao_5s_pct": _pct(recov_5s, len(losses)),
            "amostra_N": int(len(losses)),
        }

    @classmethod
    def block_set_pieces(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        tm = cls._time_mask(df, sc)
        out = {}
        for who in (team, opp):
            ev = df[(df["team_name"] == who) & tm]
            corners = ev[ev.get("pass_type_name") == "Corner"]
            sp_shots = ev[(ev["type_name"] == "Shot") & ev.get("play_pattern_name").isin(
                ["From Corner", "From Free Kick", "From Throw In"])]
            out[who] = {"escanteios": int(len(corners)), "finalizacoes_de_bola_parada": int(len(sp_shots)),
                        "xg_bola_parada": _r(sp_shots["shot_statsbomb_xg"].sum(), 2)}
        return out

    @classmethod
    def block_player(cls, df: pd.DataFrame, sc: QueryScope, player: str) -> Dict[str, Any]:
        tm = cls._time_mask(df, sc)
        ev = df[(df["player_name"] == player) & tm]
        if sc.side or sc.third:
            ev = ev[cls._zone_mask(ev, sc)]
        passes = ev[ev["type_name"] == "Pass"]
        comp = passes[passes["is_pass_completed"] == 1]
        shots = ev[ev["type_name"] == "Shot"]
        duels = ev[ev["type_name"].isin(["Duel", "Dribble"])]
        won = duels[duels.get("duel_outcome_name").isin(["Won", "Success", "Complete", "Success In Play"])]
        team_series = df.loc[df["player_name"] == player, "team_name"].dropna()
        team = team_series.iloc[0] if not team_series.empty else ""
        received = df[(df["pass_recipient_name"] == player) & tm & (df["is_pass_completed"] == 1)]
        return {
            "jogador": player,
            "equipe": team,
            "acoes": int(len(ev)),
            "posicao_media_xy": [_r(ev["x"].mean(), 1), _r(ev["y"].mean(), 1)] if len(ev) else None,
            "passes": int(len(passes)),
            "precisao_passe_pct": _pct(len(comp), len(passes)),
            "passes_progressivos": int((comp.get("is_progressive_action", pd.Series(dtype=int)) == 1).sum()),
            "quebras_de_linha": int((comp.get("is_line_breaking_pass", pd.Series(dtype=int)) == 1).sum()),
            "xt_gerado": _r(comp["delta_xt"].clip(lower=0).sum(), 3) if "delta_xt" in comp else None,
            "finalizacoes": int(len(shots)),
            "xg": _r(shots["shot_statsbomb_xg"].sum(), 2),
            "duelos": int(len(duels)),
            "duelos_ganhos_pct": _pct(len(won), len(duels)),
            "perdas_de_posse": int((ev["is_turnover"] == 1).sum()),
            "recuperacoes": int((ev["is_ball_recovery"] == 1).sum()),
            "quem_mais_o_abastece": received.groupby("player_name").size().sort_values(ascending=False).head(2).to_dict(),
            "para_quem_mais_passa": comp.groupby("pass_recipient_name").size().sort_values(ascending=False).head(2).to_dict(),
            "amostra_N": int(len(ev)),
        }

    @classmethod
    def block_possession(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        tm = cls._time_mask(df, sc)
        p = df[tm & (df["type_name"] == "Pass")]
        f3 = p[p["x"] >= 80]
        return {
            "share_passes_pct": _pct((p["team_name"] == team).sum(), len(p)),
            "field_tilt_pct": _pct((f3["team_name"] == team).sum(), len(f3)),
            "passes": {team: int((p["team_name"] == team).sum()), opp: int((p["team_name"] == opp).sum())},
            "amostra_N": int(len(p)),
        }

    # ------------------------------------------------------- montagem
    @classmethod
    def build(cls, df: pd.DataFrame, sc: QueryScope, target_team: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        teams = [t for t in df["team_name"].dropna().unique().tolist()]
        opp = next((t for t in teams if t != target_team), "Adversário")
        team, other = (opp, target_team) if sc.team_focus == "opponent" else (target_team, opp)

        blocks: Dict[str, Any] = {"contexto": cls.block_context(df, sc, team, other)}
        m = set(sc.metrics)
        phase = sc.phase
        if sc.players:
            for p in sc.players:
                blocks[f"jogador::{p}"] = cls.block_player(df, sc, p)
        if phase in ("defensive", "both") or (m & {"compactness"}) or (not phase and sc.side and not sc.players):
            blocks["defesa_no_recorte"] = cls.block_defense(df, sc, team, other)
        if phase in ("offensive", "both") or (not phase and m & {"shots", "passing", "progression", "crosses"}):
            blocks["ataque_no_recorte"] = cls.block_attack(df, sc, team)
        if m & {"pressing", "recoveries"} or phase == "transition":
            blocks["pressao"] = cls.block_pressing(df, sc, team, other)
        if phase == "transition" or m & {"turnovers"}:
            blocks["transicao"] = cls.block_transition(df, sc, team, other)
        if phase == "set_pieces" or m & {"set_pieces"}:
            blocks["bola_parada"] = cls.block_set_pieces(df, sc, team, other)
        if m & {"possession"}:
            blocks["posse"] = cls.block_possession(df, sc, team, other)
        if len(blocks) == 1:  # pergunta genérica: visão curta do jogo no recorte
            blocks["posse"] = cls.block_possession(df, sc, team, other)
            blocks["ataque_no_recorte"] = cls.block_attack(df, sc, team)
            blocks["ataque_adversario"] = cls.block_attack(df, sc, other)

        roster = sorted(df["player_name"].dropna().astype(str).unique().tolist())
        return {
            "metadata": {
                "match_id": int(meta.get("match_id", 0) or 0),
                "target_team": team,
                "opponent_team": other,
                "data_level": meta.get("data_level", "EVENTS"),
                "data_source": meta.get("data_source", ""),
                "is_simulation_data": meta.get("data_level") == "SIMULATED",
                "user_query": sc.raw,
                "match_player_roster": roster,
            },
            "escopo": sc.to_dict(),
            "blocos": blocks,
        }

    @classmethod
    def build_boxscore(cls, box: Dict[str, Any], sc: QueryScope, meta: Dict[str, Any], target_team: str) -> Dict[str, Any]:
        stats = box.get("team_stats", pd.DataFrame())
        tl = box.get("timeline", pd.DataFrame())
        lu = box.get("lineups", pd.DataFrame())
        ps = box.get("player_stats", pd.DataFrame())
        table: Dict[str, Dict[str, Any]] = {}
        for r in stats.itertuples() if not stats.empty else []:
            table.setdefault(r.stat_label, {})[r.team_name] = r.value
        events = []
        if not tl.empty:
            t = tl.copy()
            if sc.minute_from is not None:
                t = t[(t["minute"] >= sc.minute_from) & (t["minute"] <= (sc.minute_to or 130))]
            if sc.period == 1:
                t = t[t["minute"] <= 45]
            elif sc.period == 2:
                t = t[t["minute"] > 45]
            events = [{"minuto": int(r.minute) if pd.notna(r.minute) else None,
                       "acrescimo": int(r.extra_minute) if pd.notna(r.extra_minute) else None,
                       "equipe": r.team_name, "tipo": r.event_type, "detalhe": r.detail,
                       "jogador": r.player_name, "relacionado": r.related_player} for r in t.itertuples()]
        players_block = []
        if not ps.empty and sc.players:
            for p in sc.players:
                row = ps[ps["player_name"] == p]
                if not row.empty:
                    r0 = row.iloc[0]
                    players_block.append({"jogador": p, "minutos": r0.get("minutes"), "nota": r0.get("rating"),
                                          **(r0.get("stats") or {})})
        roster = (set(lu["player_name"].tolist() if not lu.empty else []) |
                        set(ps["player_name"].tolist() if not ps.empty else []) |
                        set(e["jogador"] for e in events if e.get("jogador")) |
                        set(e["relacionado"] for e in events if e.get("relacionado")))
        roster = {r for r in roster if isinstance(r, str)}
        return {
            "metadata": {
                "match_id": int(meta.get("match_id", 0) or 0),
                "target_team": target_team,
                "opponent_team": meta.get("away_team_name") if meta.get("home_team_name") == target_team else meta.get("home_team_name"),
                "data_level": meta.get("data_level", "BOXSCORE"),
                "data_source": meta.get("data_source", ""),
                "placar": f"{meta.get('home_team_name')} {meta.get('home_score')} x {meta.get('away_score')} {meta.get('away_team_name')}",
                "user_query": sc.raw,
                "match_player_roster": sorted(r for r in roster if isinstance(r, str) and r.strip()),
            },
            "escopo": sc.to_dict(),
            "blocos": {
                "estatisticas_dos_times": table,
                "linha_do_tempo_no_recorte": events,
                "atletas_citados": players_block,
                "limitacao": ("A fonte desta partida não traz coordenadas: perguntas sobre lado do campo, "
                              "compactação, redes de passes ou xT não podem ser respondidas com dados reais."
                              if sc.needs_spatial else ""),
            },
        }
