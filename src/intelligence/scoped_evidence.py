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


TACTICAL_ASKS = {"corridors", "conceded_how", "between_lines", "efficiency", "moments", "goal_buildup",
                 "defenders_diag", "combinations", "attack_plan"}


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
                {"minuto": int(r.minute) + 1, "equipe": r.team_name, "jogador": r.player_name}
                for r in goals.itertuples()
            ] + [{"minuto": int(r.minute) + 1, "equipe": opp if r.team_name == team else team, "jogador": f"gol contra de {r.player_name}"}
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
        # "mais passes" usa exatamente a mesma contagem do ranking de passes (todos os passes tentados, sem
        # conduções nem recepções) — assim a mesma pergunta nunca dá dois números diferentes
        actors = passes[passes["player_name"].notna()].groupby("player_name").size().sort_values(ascending=False)
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
            "protagonistas_no_setor": [{"jogador": k, "acoes": int(v), "passes": int(v)} for k, v in actors.head(3).items()],
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
        # duelos com resultado registrado: desarmes (Duel/Tackle). Dribles e duelos aéreos são contados à parte,
        # porque a fonte não informa o resultado do drible e só registra o duelo aéreo perdido.
        duels = ev[(ev["type_name"] == "Duel") & (ev.get("duel_type_name") == "Tackle")]
        won = duels[duels.get("duel_outcome_name").isin(["Won", "Success", "Complete", "Success In Play", "Success Out"])]
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
            "dribles_tentados": int((ev["type_name"] == "Dribble").sum()),
            "duelos_aereos_perdidos": int(((ev["type_name"] == "Duel") & (ev.get("duel_type_name") == "Aerial Lost")).sum()),
            "perdas_de_posse": int((ev["is_turnover"] == 1).sum()),
            "recuperacoes": int((ev["is_ball_recovery"] == 1).sum()),
            "gols": int(((shots.get("shot_outcome_name") == "Goal")).sum()) if len(shots) else 0,
            "minutos_dos_gols": [int(m) + 1 for m in shots.loc[shots.get("shot_outcome_name") == "Goal", "minute"]] if len(shots) else [],
            "finalizacoes_no_alvo": int(shots.get("shot_outcome_name", pd.Series(dtype=object)).isin(["Goal", "Saved", "Saved To Post"]).sum()),
            "finalizacoes_dentro_da_area": int(((shots["x"] >= 102) & (shots["y"].between(18, 62))).sum()) if len(shots) else 0,
            "zonas_onde_mais_atuou": cls._top_zones(ev, "x", "y", 2),
            "zonas_onde_recebeu": cls._top_zones(received, "end_x", "end_y", 2) if "end_x" in received else [],
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
            "share_passes_pct_adversario": _pct((p["team_name"] == opp).sum(), len(p)),
            "field_tilt_pct": _pct((f3["team_name"] == team).sum(), len(f3)),
            "field_tilt_pct_adversario": _pct((f3["team_name"] == opp).sum(), len(f3)),
            "passes": {team: int((p["team_name"] == team).sum()), opp: int((p["team_name"] == opp).sum())},
            "amostra_N": int(len(p)),
        }

    # ------------------------------------------------- fatos e rankings
    @classmethod
    def block_goals(cls, df: pd.DataFrame, team: str, opp: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        from src.metrics.match_facts import goals, shootout

        g = goals(df)
        return {"placar": {team: sum(1 for x in g if x["equipe"] == team), opp: sum(1 for x in g if x["equipe"] == opp)},
                "gols": g, "disputa_de_penaltis": shootout(df),
                "nota": "assistência = último passe certo da equipe para o autor do gol na mesma posse"}

    @classmethod
    def block_ranking(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str, top: int = 5) -> Dict[str, Any]:
        from src.metrics.match_facts import PLAYER_STAT_LABELS, player_match_stats

        metric = sc.ranking_metric or "xt"
        w = df[cls._time_mask(df, sc)]
        if metric == "erros_perigosos":
            from src.intelligence.tactical_blocks import dangerous_errors

            scope = team if sc.team_named else None
            return {"metrica": "Erros que viraram finalização do rival", "chave": metric,
                    "erros_perigosos": dangerous_errors(w, scope, sc.position_filter), "lideres": [],
                    "equipes_consideradas": scope or f"{team} e {opp}", "amostra_N": int(len(w))}
        if metric == "perigo_ia":
            return cls.block_danger_ranking(w, sc, team, opp, top)
        if sc.side or sc.third:
            w = w[cls._zone_mask(cls._own_frame(w, team), sc)]
        scope_team = None
        if sc.team_named and sc.team_focus in ("target", "opponent"):
            scope_team = team
        # E5: se a fonte nem registra esse tipo de lance, a resposta é "não tenho esse dado", não "ninguém fez"
        need = {"pressoes": ("Pressure",), "erros_diretos": ("Error",), "conducoes": ("Carry",),
                "xg": None, "faltas_sofridas": ("Foul Won",)}.get(metric)
        if metric == "xg" and ("shot_statsbomb_xg" not in df or pd.to_numeric(df["shot_statsbomb_xg"], errors="coerce").notna().sum() == 0) \
                and (df["type_name"] == "Shot").any():
            return {"metrica": PLAYER_STAT_LABELS.get(metric, metric), "lideres": [], "amostra_N": 0,
                    "sem_dado": "esta fonte"}
        if need and not df["type_name"].isin(need).any():
            return {"metrica": PLAYER_STAT_LABELS.get(metric, metric), "lideres": [], "amostra_N": 0,
                    "sem_dado": "esta fonte"}
        st = player_match_stats(w, scope_team)
        if st.empty:
            return {"metrica": PLAYER_STAT_LABELS.get(metric, metric), "lideres": [], "amostra_N": 0}
        if sc.position_filter:
            from src.metrics.player_rating import sector

            st = st[st["posicao"].map(sector) == sc.position_filter]
        st = st[st[metric].fillna(0) > 0].sort_values([metric, "minutos"], ascending=[False, True]).head(top)
        extra = {"finalizacoes_no_alvo": "finalizacoes", "passes_certos": "passes", "gols": "finalizacoes",
                 "assistencias": "passes_decisivos", "perigo": "xg", "passes_errados": "passes"}.get(metric)
        ia = {}
        if metric == "perigo":   # xT + xG por jogador; a rede neural entra como segunda opinião
            try:
                ia = {"segunda_opiniao_ia": cls.block_danger_ranking(df[cls._time_mask(df, sc)], sc, team, opp, 3)}
            except Exception:
                ia = {}
        return {**ia, "metrica": PLAYER_STAT_LABELS.get(metric, metric), "chave": metric,
                "equipes_consideradas": scope_team or f"{team} e {opp}",
                "lideres": [{"jogador": r.jogador, "equipe": r.equipe, "valor": _r(getattr(r, metric), 3),
                             **({"secundaria": PLAYER_STAT_LABELS[extra], "valor_secundario": _r(getattr(r, extra), 3)} if extra else {})}
                            for r in st.itertuples()],
                "amostra_N": int(len(w))}

    @staticmethod
    def _scored(df: pd.DataFrame) -> pd.DataFrame:
        from src.machine_learning.model_registry import champion_cached, score_actions

        try:
            return score_actions(df, champion_cached())
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _model_card() -> Optional[Dict[str, Any]]:
        from src.machine_learning.model_registry import model_card

        try:
            return model_card()
        except Exception:
            return None

    @classmethod
    def block_danger_ranking(cls, w: pd.DataFrame, sc: QueryScope, team: str, opp: str, top: int = 5) -> Dict[str, Any]:
        from src.machine_learning.model_registry import DANGER_THRESHOLD, danger_by_player

        card = cls._model_card()
        sco = cls._scored(w)
        scope_team = team if sc.team_named and sc.team_focus in ("target", "opponent") else None
        return {"metrica": "Perigo criado (rede neural)", "chave": "perigo_ia", "modelo": card,
                "limiar_pct": int(100 * DANGER_THRESHOLD), "equipes_consideradas": scope_team or f"{team} e {opp}",
                "lideres_ia": danger_by_player(sco, scope_team, top) if not sco.empty else [],
                "acoes_avaliadas": int(len(sco)), "amostra_N": int(len(sco))}

    @classmethod
    def block_result(cls, df: pd.DataFrame, team: str, opp: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        from src.metrics.match_facts import TEAM_STAT_LABELS, team_match_stats

        a, b = team_match_stats(df, team), team_match_stats(df, opp)
        keys = ["gols", "xg", "finalizacoes", "finalizacoes_no_alvo", "share_passes_pct", "field_tilt_pct", "ppda",
                "entradas_na_area", "passes_progressivos", "recuperacoes", "perdas_de_posse"]
        from src.metrics.match_facts import shootout

        return {"comparativo": {TEAM_STAT_LABELS[k]: {team: a.get(k), opp: b.get(k)} for k in keys},
                "disputa_de_penaltis": shootout(df),
                "gols": cls.block_goals(df, team, opp, meta)["gols"],
                "nota": "PPDA estimado: passes adversários na construção ÷ ações defensivas da equipe no campo adversário"}

    # ------------------------------------------------------------- planos
    @staticmethod
    def _zone_name(x: float, y: float) -> str:
        third = "terço defensivo" if x < 40 else ("terço médio" if x < 80 else "terço ofensivo")
        lane = "esquerda" if y < 30 else ("centro" if y < 50 else "direita")
        return f"{third} — {lane}"

    @classmethod
    def _top_zones(cls, d: pd.DataFrame, xc: str = "x", yc: str = "y", n: int = 2) -> List[Dict[str, Any]]:
        d = d.dropna(subset=[xc, yc])
        if d.empty:
            return []
        z = d.apply(lambda r: cls._zone_name(r[xc], r[yc]), axis=1).value_counts()
        return [{"zona": k, "acoes": int(v), "pct": _pct(v, len(d))} for k, v in z.head(n).items()]

    @classmethod
    def block_plan_vs_player(cls, df: pd.DataFrame, sc: QueryScope, player: str) -> Dict[str, Any]:
        """Como anular um atleta: por onde e de quem ele recebe, onde age, o que gera e quem o marca."""
        w = df[cls._time_mask(df, sc)]
        own_team = w.loc[w["player_name"] == player, "team_name"].dropna()
        if own_team.empty:
            return {"jogador": player, "jogou": False}
        team = str(own_team.iloc[0])
        rival = next((t for t in w["team_name"].dropna().unique() if t != team), "adversário")
        rec = w[(w["type_name"] == "Pass") & (w.get("pass_recipient_name") == player) & (w["pass_outcome_name"].isna())]
        acts = w[w["player_name"] == player]
        feeders = rec["player_name"].value_counts().head(3)
        shots = acts[acts["type_name"] == "Shot"]
        drib = acts[acts["type_name"] == "Dribble"]
        lost = acts[acts.get("is_turnover", 0) == 1] if "is_turnover" in acts else acts.iloc[0:0]
        fouls_on = w[(w["type_name"] == "Foul Won") & (w["player_name"] == player)]
        p = cls.block_player(df, sc, player)
        return {
            "jogador": player, "jogou": True, "equipe": team, "quem_defende": rival,
            "passes_recebidos": int(len(rec)),
            "zonas_onde_recebe": cls._top_zones(rec, "end_x", "end_y"),
            "quem_mais_o_abastece": {k: int(v) for k, v in feeders.items()},
            "zonas_onde_age": cls._top_zones(acts),
            "finalizacoes": int(len(shots)), "xg": _r(pd.to_numeric(shots.get("shot_statsbomb_xg"), errors="coerce").sum()),
            "dribles": int(len(drib)), "faltas_sofridas": int(len(fouls_on)), "perdas_de_posse": int(len(lost)),
            "xt_gerado": p.get("xt_gerado"), "passes_progressivos": p.get("passes_progressivos"),
            "para_quem_mais_passa": p.get("para_quem_mais_passa"),
            "amostra_N": int(len(acts)),
            **cls._danger_for_player(w, player),
        }

    @classmethod
    def _danger_for_player(cls, w: pd.DataFrame, player: str) -> Dict[str, Any]:
        from src.machine_learning.model_registry import DANGER_THRESHOLD

        sco = cls._scored(w)
        card = cls._model_card()
        if sco.empty or not card:
            return {}
        mine = sco[sco["player_name"] == player]
        hot = mine[mine["p_perigo"] >= DANGER_THRESHOLD]
        return {"ia": {"modelo": card, "acoes_avaliadas": int(len(mine)), "acoes_perigosas": int(len(hot)),
                       "limiar_pct": int(100 * DANGER_THRESHOLD),
                       "zonas_das_acoes_perigosas": cls._top_zones(hot, "x", "y", 2),
                       "maior_chance_pct": round(100 * float(mine["p_perigo"].max()), 1) if len(mine) else None}}

    @classmethod
    def block_plan_team(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        """Plano para `team` diante de `opp`: por onde opp criou perigo, quem criou, onde team perdeu a bola."""
        from src.metrics.match_facts import player_match_stats, team_match_stats

        w = df[cls._time_mask(df, sc)]
        f = cls._own_frame(w, opp)                  # referencial de quem ataca (opp)
        o = f[f["team_name"] == opp]
        entries = o[o.get("is_box_entry", 0) == 1] if "is_box_entry" in o else o.iloc[0:0]
        shots = o[o["type_name"] == "Shot"]
        crosses = o[(o["type_name"] == "Pass") & (o.get("is_pass_cross", 0).fillna(0).astype(bool))]
        ps = player_match_stats(w, opp)
        creators = ps.sort_values("xt", ascending=False).head(3) if not ps.empty else ps
        g = cls._own_frame(w, team)
        own = g[g["team_name"] == team]
        losses = own[own.get("is_turnover", 0) == 1] if "is_turnover" in own else own.iloc[0:0]
        own_half_losses = losses[losses["x"] < 60]
        tr = cls.block_transition(df, sc, team, opp)
        a, b = team_match_stats(w, team), team_match_stats(w, opp)
        return {
            "equipe": team, "adversario": opp,
            "corredores_das_entradas_na_area_do_adversario": cls._top_zones(entries, "x", "y", 3),
            "entradas_na_area_do_adversario": int(len(entries)),
            "finalizacoes_do_adversario": int(len(shots)), "xg_do_adversario": b.get("xg"),
            "zonas_das_finalizacoes_do_adversario": cls._top_zones(shots, "x", "y", 2),
            "cruzamentos_do_adversario": int(len(crosses)),
            "criadores_do_adversario": [{"jogador": r.jogador, "xt": _r(r.xt, 3), "passes": int(r.passes)}
                                        for r in creators.itertuples()],
            "perdas_de_posse": int(len(losses)), "perdas_no_proprio_campo": int(len(own_half_losses)),
            "zonas_das_perdas": cls._top_zones(own_half_losses, "x", "y", 2),
            "finalizacoes_adversarias_ate_15s_apos_perda": tr.get("finalizacoes_adversarias_em_ate_15s_apos_perda"),
            "posse_pct": {team: a.get("share_passes_pct"), opp: b.get("share_passes_pct")},
            "precisao_passe_pct": {team: a.get("precisao_passe_pct"), opp: b.get("precisao_passe_pct")},
            "ppda": {team: a.get("ppda"), opp: b.get("ppda")},
            "gols": {team: a.get("gols"), opp: b.get("gols")},
            "amostra_N": int(len(w)),
            **cls._danger_for_team(w, opp),
        }

    @classmethod
    def _danger_for_team(cls, w: pd.DataFrame, attacker: str) -> Dict[str, Any]:
        from src.machine_learning.model_registry import DANGER_THRESHOLD, danger_by_player, danger_zones

        sco = cls._scored(w)
        card = cls._model_card()
        if sco.empty or not card:
            return {}
        return {"ia": {"modelo": card, "limiar_pct": int(100 * DANGER_THRESHOLD),
                       "zonas_perigosas_do_adversario": danger_zones(sco, attacker),
                       "mais_perigosos_do_adversario": danger_by_player(sco, attacker, 3)}}

    # ------------------------------------------------------- perfil dos atletas (fora dos eventos)
    _tm_cache: Dict[str, Any] = {}

    @classmethod
    def _tm_players(cls) -> pd.DataFrame:
        """Cadastro do Transfermarkt no data lake (altura, nascimento, valor). Vazio se o lake não tiver a tabela."""
        try:
            from src.data_lake.lake import Lake

            lake = Lake(sqlite_path=None)
            if not lake.exists("tm_jogadores"):
                return pd.DataFrame()
            path = lake.path("tm_jogadores")
            key = f"{path}:{path.stat().st_mtime}"
            if cls._tm_cache.get("key") != key:
                tm = lake.read("tm_jogadores")
                from src.intelligence.query_understanding import norm

                tm = tm.assign(_n=tm["nome"].map(norm))
                tm["_fl"] = tm["_n"].str.split().map(lambda w: f"{w[0]} {w[-1]}" if len(w) > 1 else (w[0] if w else ""))
                cls._tm_cache = {"key": key, "df": tm}
            return cls._tm_cache["df"]
        except Exception:
            return pd.DataFrame()

    @classmethod
    def block_profile(cls, df: pd.DataFrame, team: str, opp: str, attr: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Altura, idade ou valor de mercado médio de quem entrou em campo. Os eventos não trazem isso: cruza os atletas
        da partida com o cadastro do Transfermarkt (nome completo, ou primeiro + último nome quando é único).
        Informa quantos atletas foram encontrados — média de poucos atletas não é média do time.
        """
        from src.intelligence.query_understanding import norm

        tm = cls._tm_players()
        col = {"altura": "altura_cm", "idade": "nascimento", "valor": "valor_mercado_eur"}[attr]
        out: Dict[str, Any] = {"atributo": attr, "fonte": "cadastro do Transfermarkt (data lake)",
                               "disponivel": not tm.empty and col in tm.columns, "equipes": {}}
        if not out["disponivel"]:
            return out
        by_n = tm.drop_duplicates("_n").set_index("_n")
        fl_counts = tm["_fl"].value_counts()
        by_fl = tm[tm["_fl"].map(fl_counts) == 1].set_index("_fl")
        d = df[df["player_name"].notna()]
        if "period" in d.columns:
            d = d[d["period"] <= 4]                       # disputa de pênaltis não conta como "entrou em campo"
        match_day = pd.to_datetime(meta.get("match_date"), errors="coerce")
        for tname in (team, opp):
            names = sorted(d.loc[d["team_name"] == tname, "player_name"].astype(str).unique())
            vals, found = [], []
            for nm in names:
                n = norm(nm)
                w = n.split()
                row = by_n.loc[n] if n in by_n.index else (by_fl.loc[f"{w[0]} {w[-1]}"] if len(w) > 1 and
                                                          f"{w[0]} {w[-1]}" in by_fl.index else None)
                if row is None:
                    continue
                v = row[col]
                if attr == "idade":
                    born = pd.to_datetime(v, errors="coerce")
                    ref = match_day if pd.notna(match_day) else pd.Timestamp.today()
                    v = (ref - born).days / 365.25 if pd.notna(born) else None
                v = pd.to_numeric(v, errors="coerce")
                if pd.notna(v) and v > 0:
                    vals.append(float(v))
                    found.append({"jogador": nm, "valor": round(float(v), 1)})
            out["equipes"][tname] = {"atletas_na_partida": len(names), "encontrados": len(vals),
                                     "media": round(float(np.mean(vals)), 1) if vals else None,
                                     "extremos": sorted(found, key=lambda r: -r["valor"])[:1] + sorted(found, key=lambda r: r["valor"])[:1]
                                     if found else []}
        return out

    # ------------------------------------------------- alvos específicos (v36)
    @classmethod
    def block_presence(cls, df: pd.DataFrame, sc: QueryScope, meta: Dict[str, Any]) -> Dict[str, Any]:
        """"Fulano jogou?" — responde pelo que a partida registra (lances, entrada/saída), sem supor."""
        from src.metrics.match_facts import _minutes

        names = list(sc.players)
        asked = sc.attribute or (names[0] if names else None)
        if not names and asked:
            import difflib

            from src.intelligence.query_understanding import norm

            roster = df["player_name"].dropna().astype(str).unique().tolist()
            nr = {norm(r): r for r in roster}
            hit = difflib.get_close_matches(norm(asked), list(nr), n=1, cutoff=0.82)
            if not hit:  # sobrenome parecido ("mbape" ≈ "mbappe")
                parts = {p: r for r in roster for p in norm(r).split() if len(p) >= 4}
                hit2 = difflib.get_close_matches(norm(asked).split()[-1], list(parts), n=1, cutoff=0.82)
                names = [parts[hit2[0]]] if hit2 else []
            else:
                names = [nr[hit[0]]]
        if not names:
            return {"pedido": asked, "jogou": False, "eventos_registrados": 0}
        p = names[0]
        ev = df[df["player_name"] == p]
        mins = _minutes(df).get(p)
        subs = df[df["type_name"] == "Substitution"] if "type_name" in df else df.iloc[0:0]
        came_in = subs[subs.get("substitution_replacement_name", pd.Series(index=subs.index, dtype=object)) == p]
        went_out = subs[subs["player_name"] == p]
        team = ev["team_name"].dropna().iloc[0] if not ev.empty else (came_in["team_name"].iloc[0] if not came_in.empty else "")
        return {"pedido": asked, "jogador": p, "equipe": team, "jogou": bool(len(ev) or len(came_in)),
                "titular": bool(len(ev)) and came_in.empty,
                "entrou_aos": int(came_in["minute"].iloc[0]) + 1 if not came_in.empty else None,
                "saiu_aos": int(went_out["minute"].iloc[0]) + 1 if not went_out.empty else None,
                "minutos_estimados": mins, "eventos_registrados": int(len(ev))}

    @classmethod
    def block_errors(cls, df: pd.DataFrame, sc: QueryScope, player: str) -> Dict[str, Any]:
        """Erros de um atleta, separados por tipo (nada somado escondido)."""
        from src.metrics.match_facts import player_match_stats

        w = df[cls._time_mask(df, sc)]
        st = player_match_stats(w)
        row = st[st["jogador"] == player]
        if row.empty:
            return {"jogador": player, "sem_dados": True}
        r = row.iloc[0]
        other_losses = max(int(r["perdas_de_posse"]) - int(r["passes_errados"]), 0)
        parts = {"passes_errados": int(r["passes_errados"]), "outras_perdas_de_bola": other_losses,
                 "erros_que_deram_finalizacao_ao_rival": int(r["erros_diretos"]),
                 "duelos_perdidos": int(r["duelos_perdidos"])}
        own = w[(w["player_name"] == player) & (w["type_name"] == "Pass") & w.get("pass_outcome_name").notna()] \
            if "pass_outcome_name" in w else w.iloc[0:0]
        own_half = int((own["x"] < 60).sum()) if "x" in own else None
        return {"jogador": player, "equipe": r["equipe"], "minutos_estimados": float(r["minutos"]),
                **parts, "total_de_erros": int(sum(parts.values())),
                "passes_tentados": int(r["passes"]), "precisao_passe_pct": None if pd.isna(r["precisao_passe_pct"]) else float(r["precisao_passe_pct"]),
                "passes_errados_no_proprio_campo": own_half,
                "faltas_cometidas": int(r["faltas_cometidas"]), "cartoes_amarelos": int(r["cartoes_amarelos"]),
                "nota": "perdas de bola = domínio errado, desarmado ou drible sem sucesso; passes errados contados à parte",
                "amostra_N": int(r["toques"])}

    @classmethod
    def _team_issues(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> List[Dict[str, Any]]:
        """Candidatos a falha tática do `team`, cada um com número próprio e peso (maior = mais grave)."""
        from src.metrics.match_facts import team_match_stats

        w = df[cls._time_mask(df, sc)]
        a, b = team_match_stats(w, team), team_match_stats(w, opp)
        tr = cls.block_transition(df, sc, team, opp)
        plan = cls.block_plan_team(df, sc, team, opp)
        sp = cls.block_set_pieces(df, sc, team, opp) if "play_pattern_name" in df else {}
        out: List[Dict[str, Any]] = []

        def add(tipo, peso, **kw):
            if peso > 0:
                out.append({"tipo": tipo, "peso": round(float(peso), 2), **kw})

        xa, xb = a.get("xg") or 0.0, b.get("xg") or 0.0
        add("cedeu_mais_chances", (xb - xa) * 3, xg_cedido=xb, xg_criado=xa,
            finalizacoes_cedidas=b.get("finalizacoes"), finalizacoes_feitas=a.get("finalizacoes"))
        n_after = tr.get("finalizacoes_adversarias_em_ate_15s_apos_perda") or 0
        tr_o = cls.block_transition(df, sc, opp, team)
        n_after_o = tr_o.get("finalizacoes_adversarias_em_ate_15s_apos_perda") or 0
        g = cls._own_frame(w, opp)
        lo = g[(g["team_name"] == opp) & (g.get("is_turnover", 0) == 1) & (g["x"] < 60)] if "is_turnover" in g else g.iloc[0:0]
        own_l, opp_l = plan.get("perdas_no_proprio_campo") or 0, int(len(lo))
        add("saida_de_bola_e_transicao", (n_after - n_after_o) * 0.8 + (own_l - opp_l) / 8,
            perdas_no_proprio_campo=own_l, perdas_no_proprio_campo_rival=opp_l, finalizacoes_rivais_ate_15s=n_after,
            finalizacoes_ate_15s_apos_roubo=n_after_o, zonas_das_perdas=plan.get("zonas_das_perdas"))
        z = plan.get("corredores_das_entradas_na_area_do_adversario") or []
        n_ent = plan.get("entradas_na_area_do_adversario") or 0
        if z and n_ent >= 4:
            top = z[0]
            share = float(top.get("pct") or 0)
            add("corredor_vulneravel", max(share - 40, 0) / 12, zona=top.get("zona"), entradas=top.get("acoes"),
                pct=top.get("pct"), entradas_totais=n_ent)
        ta, tb = a.get("field_tilt_pct"), b.get("field_tilt_pct")
        if ta is not None and tb is not None:
            add("pouca_presenca_no_campo_rival", (tb - ta) / 15, field_tilt=ta, field_tilt_rival=tb,
                entradas_na_area=a.get("entradas_na_area"), entradas_na_area_rival=b.get("entradas_na_area"))
        pa, pb = a.get("ppda"), b.get("ppda")
        if pa and pb:
            add("pressao_frouxa", (pa / pb - 1.2) * 1.5, ppda=pa, ppda_rival=pb)
        ga = a.get("gols") or 0
        if (a.get("finalizacoes") or 0) >= 3:
            add("finalizacao_ruim", (xa - ga) * 1.2 + (0.4 if (a.get("finalizacoes_no_alvo") or 0) <= 1 else 0),
                gols=ga, xg=xa, finalizacoes=a.get("finalizacoes"), no_alvo=a.get("finalizacoes_no_alvo"))
        pra, prb = a.get("precisao_passe_pct"), b.get("precisao_passe_pct")
        if pra is not None and prb is not None:
            add("passe_impreciso", (prb - pra) / 4, precisao=pra, precisao_rival=prb)
        xsp = (sp.get(opp) or {}).get("xg_bola_parada")
        if xsp:
            add("bola_parada_defensiva", float(xsp) * 2.5, xg_rival_em_bola_parada=xsp)
        return sorted(out, key=lambda d: -d["peso"])

    @classmethod
    def block_weakness(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        issues = cls._team_issues(df, sc, team, opp)
        return {"equipe": team, "adversario": opp, "falhas": issues[:4], "amostra_N": int(len(df)),
                "criterio": "cada falha é comparada com o que o rival fez no mesmo jogo; a mais grave vem primeiro"}

    @classmethod
    def block_strength(cls, df: pd.DataFrame, sc: QueryScope, team: str, opp: str) -> Dict[str, Any]:
        """Pontos fortes do `team` = as falhas que ele provocou no rival (mesmos critérios, lado espelhado)."""
        issues = cls._team_issues(df, sc, opp, team)
        return {"equipe": team, "adversario": opp, "fortes": issues[:4], "amostra_N": int(len(df)),
                "criterio": "o que a equipe impôs ao rival no mesmo jogo (mesma régua das falhas, lado trocado)"}

    @staticmethod
    def _defender(sc: QueryScope, team: str, other: str) -> str:
        """Quem DEFENDE na pergunta: o time citado depois de 'defesa/dificuldades/fraquezas/espaços'."""
        import re as _re

        from src.intelligence.query_understanding import DEMONYMS, QueryUnderstanding, norm as _n

        t = _n(sc.raw)
        for rx, c in DEMONYMS.items():
            t = _re.sub(rx, c, t)
        m = _re.search(r"(defesa|defensiv\w*|dificuldades?|fraquezas?|fragilidades?|espacos?|linha defensiva|zaga)", t)
        if m:
            tail = t[m.start():]
            pos = {tm: QueryUnderstanding._team_position(tail, tm) for tm in (team, other)}
            hit = [tm for tm, p in sorted(pos.items(), key=lambda kv: (kv[1] is None, kv[1] or 0)) if p is not None]
            if hit:
                return hit[0]
        return team

    @classmethod
    def block_tactical(cls, df: pd.DataFrame, sc: QueryScope, team: str, other: str) -> Dict[str, Any]:
        from src.intelligence import tactical_blocks as T

        w = df[cls._time_mask(df, sc)]
        a = sc.ask
        if a == "corridors":
            return {"corredores": T.corridors(w, team)}
        if a == "conceded_how":
            dfd = cls._defender(sc, team, other) if sc.team_named else team
            return {"como_sofreu": T.conceded_how(w, dfd, other if dfd == team else team)}
        if a == "between_lines":
            dfd = cls._defender(sc, team, other)
            att = other if dfd == team else team
            return {"entre_linhas": T.between_lines(w, att, dfd)}
        if a == "efficiency":
            return {"eficiencia": T.efficiency(w, [team, other])}
        if a == "moments":
            return {"momentos": {**T.moments(w, [team, other]), "foco": team}}
        if a == "goal_buildup":
            return {"jogadas_dos_gols": T.goal_buildup(w, team)}
        if a == "defenders_diag":
            return {"defensores": T.defenders_diag(w, team)}
        if a == "combinations":
            return {"duplas": T.combinations(w, team if sc.team_named else None)}
        if a == "attack_plan":
            dfd = cls._defender(sc, team, other)
            return {"plano_ataque": T.attack_plan(w, other if dfd == team else team, dfd)}
        return {}

    # ------------------------------------------------------- montagem
    @classmethod
    def build(cls, df: pd.DataFrame, sc: QueryScope, target_team: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        teams = [t for t in df["team_name"].dropna().unique().tolist()]
        opp = next((t for t in teams if t != target_team), "Adversário")
        team, other = (opp, target_team) if sc.team_focus == "opponent" else (target_team, opp)

        blocks: Dict[str, Any] = {"contexto": cls.block_context(df, sc, team, other)}
        if sc.absent and not sc.players and sc.ask in (None, "plan", "presence"):
            blocks["ausente"] = {"nomes": sc.absent, "elenco_da_partida": int(df["player_name"].nunique())}
            return cls._wrap(df, sc, team, other, meta, blocks)
        if sc.ask == "profile":
            blocks["perfil"] = cls.block_profile(df, team, other, sc.attribute or "altura", meta)
        elif sc.ask == "unavailable":
            blocks["indisponivel"] = {"pedido": sc.attribute}
        elif sc.ask == "goals":
            blocks["gols"] = cls.block_goals(df, team, other, meta)
            if sc.goal_order:
                blocks["gols"]["ordem_pedida"] = sc.goal_order
        elif sc.ask == "ranking":
            blocks["ranking"] = cls.block_ranking(df, sc, team, other)
        elif sc.ask == "result":
            blocks["resultado"] = cls.block_result(df, team, other, meta)
        elif sc.ask == "presence":
            blocks["presenca"] = cls.block_presence(df, sc, meta)
        elif sc.ask == "errors":
            for p in sc.players[:2]:
                blocks[f"erros::{p}"] = cls.block_errors(df, sc, p)
        elif sc.ask in TACTICAL_ASKS:
            blocks.update(cls.block_tactical(df, sc, team, other))
        elif sc.ask == "weakness":
            blocks["falhas"] = cls.block_weakness(df, sc, team, other)
        elif sc.ask == "strength":
            blocks["fortes"] = cls.block_strength(df, sc, team, other)
        elif sc.ask == "plan":
            if sc.players:
                for p in sc.players[:2]:
                    blocks[f"plano_jogador::{p}"] = cls.block_plan_vs_player(df, sc, p)
            else:
                blocks["plano_equipe"] = cls.block_plan_team(df, sc, team, other)
        if sc.ask:
            if sc.also_weakness:
                blocks["falhas"] = cls.block_weakness(df, sc, team, other)
            return cls._wrap(df, sc, team, other, meta, blocks)
        m = set(sc.metrics)
        phase = sc.phase
        if sc.players:
            for p in sc.players:
                blocks[f"jogador::{p}"] = cls.block_player(df, sc, p)
            if len(sc.players) >= 2:
                blocks["comparacao"] = {"jogadores": sc.players[:3]}
            if sc.also_weakness:
                wk_team = team
                blocks["falhas"] = cls.block_weakness(df, sc, wk_team, other)
            # pergunta sobre jogador: NÃO despeja o bloco do time junto (só se a pergunta pedir a equipe explicitamente)
            if not (sc.team_named and phase and not sc.also_weakness):
                return cls._wrap(df, sc, team, other, meta, blocks)
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
        generic = len(blocks) == 1
        if generic:  # pergunta genérica: visão curta do jogo no recorte
            blocks["posse"] = cls.block_possession(df, sc, team, other)
            blocks["ataque_no_recorte"] = cls.block_attack(df, sc, team)
            blocks["ataque_adversario"] = cls.block_attack(df, sc, other)
        out = cls._wrap(df, sc, team, other, meta, blocks)
        out["escopo"]["resumo_generico"] = generic
        return out

    @staticmethod
    def _wrap(df, sc, team, other, meta, blocks) -> Dict[str, Any]:
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
        opp = meta.get("away_team_name") if meta.get("home_team_name") == target_team else meta.get("home_team_name")
        extra: Dict[str, Any] = {}
        if sc.ask == "profile":
            who = lu if not lu.empty else ps
            frame = who[["player_name", "team_name"]] if not who.empty else pd.DataFrame(columns=["player_name", "team_name"])
            extra["perfil"] = cls.block_profile(frame, target_team, opp, sc.attribute or "altura", meta)
        elif sc.ask == "unavailable":
            extra["indisponivel"] = {"pedido": sc.attribute}
        if sc.goal_order:
            gls = [e for e in events if e["tipo"] in ("Goal", "goal")]
            extra["gol_pedido"] = {"ordem": sc.goal_order, "gols": gls}
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
                "leitura": _leitura(stats, meta, target_team),
                "linha_do_tempo_no_recorte": events,
                "atletas_citados": players_block,
                **extra,
                "limitacao": ("A fonte desta partida não traz coordenadas: perguntas sobre lado do campo, "
                              "compactação, redes de passes ou xT não podem ser respondidas com dados reais."
                              if sc.needs_spatial else ""),
            },
        }


def _leitura(stats: pd.DataFrame, meta: Dict[str, Any], team: str) -> Dict[str, Any]:
    """Pontos fortes/fracos derivados das estatísticas (mesma regra da tela do Match Center)."""
    if stats is None or stats.empty or not team:
        return {}
    from src.metrics.box_facts import box_facts

    home = meta.get("home_team_name")
    opp = meta.get("away_team_name") if team == home else home
    gf, ga = (meta.get("home_score"), meta.get("away_score")) if team == home else (meta.get("away_score"), meta.get("home_score"))
    try:
        good, bad = box_facts(stats, team, opp, gf, ga)
    except Exception:
        return {}
    return {"equipe": team, "fortes": [t for t, _, _ in good], "fracos": [t for t, _, _ in bad]}
