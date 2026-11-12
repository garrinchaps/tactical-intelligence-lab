"""
Módulo Construtor de Relatórios Táticos Simples, Aprofundados e Focados no Comando (Camada 8)
Inclui:
1. Resolução Inteligente de Jogadores por Nome Comum OU por Papel Tático ('o meia adversário', 'o volante').
2. Motor de Discrepância contra a Média Normal de Partidas (Bola Aérea, Cruzamentos, Pressão, Zona 14).
3. Integração com IA Generativa (Gemini 2.5 Flash) e Guardião Anti-Alucinação Numérica.
4. Relatório Duplo: Conclusões Simples em Linguagem Comum + Dossiê Aprofundado + Decisão Final.
5. Relatório Histórico de Múltiplos Jogos de um Mesmo Time e Relatório Individual de Jogadores.
"""

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from google import genai
from google.genai import types

from src.ingestion.brazil_and_multi_source import PlayerNameNormalizer
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.networks.pass_network import PassingNetworkAnalyzer
from src.metrics.xt_model import ExpectedThreatModel
from src.machine_learning.clustering import SpatialTacticalClustering
from src.machine_learning.supervised import PossessionDangerClassifier
from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.tactical_engine.diagnostic_engine import TacticalDiagnosticEngine


class QueryIntentRouter:
    """
    Roteador Neural e Semântico de Linguagem Natural.
    Identifica jogadores citados pelo nome comum (ou Fuzzy) OU pelo papel tático
    ('o meia adversário', 'o volante deles', 'o centroavante').
    """

    _nlp_instance = None

    # Mapeamento de termos em Português para as posições do StatsBomb
    ROLE_KEYWORDS_TO_POSITIONS: List[Tuple[List[str], List[str], str]] = [
        (
            ["meia", "armador", "camisa 10", "enganche", "meio-campista ofensivo", "criador"],
            ["Attacking Midfield", "Center Midfield", "Left Midfield", "Right Midfield"],
            "Meia-Armador / Criador",
        ),
        (
            ["volante", "primeiro volante", "segundo volante", "cabeça de área", "pivô", "pivo"],
            ["Defensive Midfield", "Center Defensive Midfield", "Center Midfield"],
            "Volante / Construtor de Base",
        ),
        (
            ["ponta", "extremo", "atacante de lado", "ala", "velocista"],
            ["Wing", "Left Wing", "Right Wing", "Wing Back"],
            "Ponta / Extremo",
        ),
        (
            ["centroavante", "atacante", "camisa 9", "artilheiro", "homem de área"],
            ["Center Forward", "Forward", "Striker", "Secondary Striker"],
            "Centroavante / Finalizador",
        ),
        (
            ["lateral", "lateral-direito", "lateral-esquerdo", "lateral direito", "lateral esquerdo"],
            ["Right Back", "Left Back", "Wing Back"],
            "Lateral",
        ),
        (
            ["zagueiro", "defensor", "beque"],
            ["Center Back", "Right Center Back", "Left Center Back"],
            "Zagueiro",
        ),
    ]

    @classmethod
    def _get_nlp(cls):
        if cls._nlp_instance is None:
            from src.intelligence.nlp_neural_router import TacticalNLPInterpreter

            cls._nlp_instance = TacticalNLPInterpreter()
        return cls._nlp_instance

    @staticmethod
    def _strip_accents(text: str) -> str:
        return "".join(
            c
            for c in unicodedata.normalize("NFD", str(text))
            if unicodedata.category(c) != "Mn"
        ).lower()

    @classmethod
    def extract_target_players(
        cls, user_query: str, available_players: List[str]
    ) -> List[str]:
        """
        Extrai jogadores mencionados nominalmente na pergunta (suporta nome comum,
        sobrenome, Fuzzy Matching e Similaridade de Cosseno).
        """
        if not user_query or not available_players:
            return []

        q_norm = cls._strip_accents(user_query)
        matched: List[str] = []

        for full_name in available_players:
            if not full_name:
                continue
            common_name = PlayerNameNormalizer.to_common_name(str(full_name))
            for candidate in (str(full_name), common_name):
                fn_norm = cls._strip_accents(candidate)
                if fn_norm in q_norm:
                    matched.append(str(full_name))
                    break
                tokens = [t for t in re.split(r"\s+|-", fn_norm) if len(t) >= 4]
                if any(re.search(rf"\b{re.escape(tok)}\b", q_norm) for tok in tokens):
                    matched.append(str(full_name))
                    break

        if matched:
            return list(dict.fromkeys(matched))

        # Busca Aproximada / Fuzzy (Difflib)
        import difflib
        query_words = [
            w for w in re.split(r"\W+", q_norm)
            if len(w) >= 4 and w not in {
                "como", "para", "anular", "marcar", "jogador", "atleta", "adversario",
                "time", "equipe", "tatica", "monte", "analise", "bola", "meia", "volante",
                "passe", "defesa", "ataque", "transicao", "lado", "onde", "ponta", "deles",
            }
        ]

        token_to_player = {}
        for full_name in available_players:
            fn_norm = cls._strip_accents(str(full_name))
            for tok in re.split(r"\s+|-", fn_norm):
                if len(tok) >= 4:
                    token_to_player[tok] = str(full_name)

        all_tokens = list(token_to_player.keys())
        for word in query_words:
            close_matches = difflib.get_close_matches(word, all_tokens, n=1, cutoff=0.45)
            if close_matches:
                matched.append(token_to_player[close_matches[0]])

        if matched:
            return list(dict.fromkeys(matched))

        try:
            nlp = cls._get_nlp()
            for word in query_words:
                hits = nlp.semantic_entity_match(word, available_players, threshold=0.38)
                if hits:
                    matched.append(hits[0][0])
        except Exception:
            pass

        return list(dict.fromkeys(matched))

    @classmethod
    def resolve_role_based_players(
        cls,
        user_query: str,
        df_events: pd.DataFrame,
        target_team: str,
        opponent_team: str,
    ) -> List[str]:
        """
        Se o usuário pediu 'o meia adversário', 'o volante deles', etc.,
        identifica o time alvo e retorna o atleta de maior destaque na função.
        """
        if not user_query or df_events.empty:
            return []

        q_norm = cls._strip_accents(user_query)
        asks_about_opponent = any(
            w in q_norm for w in ["adversario", "adversária", "deles", "oponente"]
        )
        team_to_search = opponent_team if asks_about_opponent else target_team

        for role_keywords, sb_positions, _ in cls.ROLE_KEYWORDS_TO_POSITIONS:
            if any(rk in q_norm for rk in role_keywords):
                team_ev = df_events[df_events["team_name"] == team_to_search]
                if team_ev.empty:
                    team_ev = df_events

                pos_mask = team_ev["position_name"].fillna("").apply(
                    lambda p: any(sp.lower() in str(p).lower() for sp in sb_positions)
                )
                role_ev = team_ev[pos_mask]
                if role_ev.empty:
                    continue

                top_in_role = (
                    role_ev["player_name"].dropna().value_counts().index.tolist()
                )
                if any(w in q_norm for w in ["dois", "dupla", "compar", "ambos"]):
                    return top_in_role[:2]
                return top_in_role[:1]

        return []

    @classmethod
    def detect_focus_with_probabilities(
        cls,
        user_query: str,
        available_players: Optional[List[str]] = None,
        role_resolved_players: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        matched_players = (
            cls.extract_target_players(user_query, available_players)
            if available_players
            else []
        )
        if not matched_players and role_resolved_players:
            matched_players = role_resolved_players

        nlp = cls._get_nlp()
        pred_info = nlp.predict_query_intent(
            user_query, matched_players_count=len(matched_players)
        )
        pred_info["matched_players"] = matched_players
        return pred_info

    @classmethod
    def detect_focus(
        cls, user_query: str, available_players: Optional[List[str]] = None
    ) -> str:
        info = cls.detect_focus_with_probabilities(user_query, available_players)
        return info["predicted_intent"]


class BenchmarkDiscrepancyEngine:
    """
    Compara os dados reais da equipe contra as médias normais de referência
    e extrai conclusões simples em linguagem comum.
    """

    NORMAL_BENCHMARKS = {
        "aerial_win_rate_pct": 50.0,
        "crosses_attempted": 14.0,
        "short_buildup_pct": 70.0,
        "ppda": 10.5,
        "zone_14_entries": 9.0,
        "box_entries": 16.0,
        "gegenpress_5s_pct": 42.0,
        "counter_attacks": 4.0,
    }

    @classmethod
    def extract_aerial_and_crossing_stats(
        cls, df_events: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        team_ev = df_events[df_events["team_name"] == target_team]

        crosses = team_ev[
            (team_ev["type_name"] == "Pass") & (team_ev.get("is_pass_cross", 0) == 1)
        ]
        n_crosses = int(len(crosses))
        comp_crosses = int(crosses["is_pass_completed"].sum()) if n_crosses > 0 else 0
        cross_acc_pct = (
            round((comp_crosses / n_crosses) * 100.0, 1) if n_crosses > 0 else 0.0
        )

        high_passes_att = team_ev[
            (team_ev["type_name"] == "Pass")
            & (team_ev.get("pass_height_name", "") == "High Pass")
            & (team_ev["end_x"] >= 80.0)
        ]

        duels = team_ev[team_ev["type_name"] == "Duel"]
        aerial_duels = duels[
            duels.get("duel_type_name", pd.Series("", index=duels.index))
            .fillna("")
            .str.contains("Aerial", case=False)
        ]

        if len(aerial_duels) >= 3:
            total_aerial = int(len(aerial_duels))
            won_aerial = int(
                aerial_duels.get("duel_outcome_name", pd.Series("", index=aerial_duels.index))
                .fillna("")
                .isin(["Won", "Success", "Success In Play"])
                .sum()
                + aerial_duels.get("duel_type_name", pd.Series("", index=aerial_duels.index))
                .fillna("")
                .str.contains("Won", case=False)
                .sum()
            )
            won_aerial = min(won_aerial, total_aerial)
        else:
            total_aerial = int(len(high_passes_att))
            won_aerial = int(high_passes_att["is_pass_completed"].sum())

        aerial_win_pct = (
            round((won_aerial / max(total_aerial, 1)) * 100.0, 1)
            if total_aerial > 0
            else 0.0
        )

        shots = team_ev[team_ev["type_name"] == "Shot"]
        head_shots = shots[
            shots.get("shot_body_part_name", pd.Series("", index=shots.index))
            .fillna("")
            .str.contains("Head", case=False)
        ]
        n_head_shots = int(len(head_shots))
        head_goals = int(
            (
                head_shots.get("shot_outcome_name", pd.Series("", index=head_shots.index))
                == "Goal"
            ).sum()
        )
        head_xg = round(float(head_shots["shot_statsbomb_xg"].fillna(0.0).sum()), 2)

        return {
            "crosses_attempted": n_crosses,
            "crosses_completed": comp_crosses,
            "cross_accuracy_pct": cross_acc_pct,
            "aerial_duels_total": total_aerial,
            "aerial_duels_won": won_aerial,
            "aerial_win_pct": aerial_win_pct,
            "headed_shots": n_head_shots,
            "headed_goals": head_goals,
            "headed_xg": head_xg,
        }

    @classmethod
    def generate_plain_language_discrepancy_conclusions(
        cls,
        df_events: pd.DataFrame,
        phases_metrics: Dict[str, Any],
        passing_network: Dict[str, Any],
        clustering_data: Dict[str, Any],
        target_team: str,
        opponent_team: str,
    ) -> Dict[str, Any]:
        d_org = phases_metrics["defensive_organization"]
        o_org = phases_metrics["offensive_organization"]
        o_tr = phases_metrics["offensive_transition"]
        d_tr = phases_metrics["defensive_transition"]

        aerial = cls.extract_aerial_and_crossing_stats(df_events, target_team)
        simple_conclusions: List[str] = []

        if (
            aerial["aerial_duels_total"] >= 6
            and (
                aerial["aerial_win_pct"] >= 55.0
                or aerial["headed_goals"] >= 1
                or aerial["headed_shots"] >= 2
            )
        ):
            goal_txt = (
                f", marcando **{aerial['headed_goals']} gol(s) de cabeça**"
                if aerial["headed_goals"] > 0
                else ""
            )
            simple_conclusions.append(
                f"🟢 **Força na Bola Aérea e Jogo Pelos Lados (Ponto Fraco de {opponent_team}):** "
                f"O **{target_team}** ganhou **{aerial['aerial_duels_won']} das {aerial['aerial_duels_total']} disputas pelo alto ({aerial['aerial_win_pct']}%)**, "
                f"explorou **{aerial['crosses_attempted']} cruzamentos** ({aerial['crosses_completed']} certos) e finalizou **{aerial['headed_shots']} vez(es) de cabeça** "
                f"(gerando {aerial['headed_xg']} xG pelo alto{goal_txt}). **Conclusão simples:** A bola aérea ofensiva funcionou muito acima da média normal (50%) e expôs a defesa do {opponent_team}."
            )
        elif aerial["crosses_attempted"] >= 15 and aerial["cross_accuracy_pct"] < 20.0:
            simple_conclusions.append(
                f"🔴 **Excesso de Cruzamentos Sem Eficiência:** O **{target_team}** insistiu em **{aerial['crosses_attempted']} cruzamentos**, "
                f"mas acertou apenas **{aerial['crosses_completed']} ({aerial['cross_accuracy_pct']}%)** e ganhou só **{aerial['aerial_win_pct']}%** pelo alto. "
                f"**Conclusão simples:** Cruzar na área foi uma escolha ruim contra a zaga do {opponent_team}; o time precisa infiltrar mais pelo chão."
            )

        ppda = float(d_org["ppda"])
        if ppda <= 8.0:
            simple_conclusions.append(
                f"🟢 **Marcação Sufocante no Campo de Ataque:** Enquanto a média normal de um jogo é deixar o adversário trocar ~10,5 passes antes de sofrer combate, "
                f"o **{target_team}** permitiu apenas **{ppda} passes por ação defensiva (PPDA)**, mantendo a linha a **{d_org['avg_defensive_engagement_height_m']} m**. "
                f"**Conclusão simples:** O time sufocou a saída de bola do {opponent_team} desde o tiro de meta."
            )
        elif ppda >= 13.5:
            simple_conclusions.append(
                f"🟡 **Defesa Passiva / Esperando Atrás:** O **{target_team}** deixou o {opponent_team} trocar **{ppda} passes por ação de combate (PPDA)** "
                f"(muito acima da média normal de 10,5). **Conclusão simples:** A equipe preferiu recuar e esperar no próprio campo em vez de pressionar a saída adversária."
            )

        vuln_sec = d_org["most_vulnerable_defensive_sector"]
        v_info = d_org["corridor_vulnerability_breakdown"].get(vuln_sec, {})
        v_share = float(v_info.get("share_of_opponent_progression_pct", 0.0))
        v_count = int(v_info.get("progressive_actions_conceded", 0))
        if v_share >= 28.0 and v_count >= 8:
            simple_conclusions.append(
                f"🔴 **Avenida Aberta na Defesa ({vuln_sec}):** Em uma defesa equilibrada, cada um dos 5 corredores sofre cerca de 20% dos avanços. "
                f"Porém, **{v_share}% de todos os avanços perigosos do {opponent_team} ({v_count} jogadas)** entraram pelo **{vuln_sec}**, gerando **{v_info.get('box_entries_conceded', 0)} invasões na grande área**. "
                f"**Conclusão simples:** Esse lado da defesa ficou desprotegido e precisa de cobertura imediata do volante."
            )

        z14 = int(o_org["zone_14_entries"])
        box_ent = int(o_org["penalty_box_entries"])
        if z14 >= 12 or box_ent >= 20:
            simple_conclusions.append(
                f"🟢 **Domínio da Entrada da Área (Zona 14):** O **{target_team}** colocou a bola **{z14} vezes na frente da área adversária** "
                f"e entrou **{box_ent} vezes dentro da grande área** (acima da referência normal de 9 e 16), usando principalmente o **{o_org['preferred_attack_corridor']}**. "
                f"**Conclusão simples:** Os volantes do {opponent_team} não fecharam a frente da área, e o {target_team} criou chances limpas pelo chão."
            )

        hub_player = passing_network.get("primary_bridge_player_betweenness", "N/A")
        vol_player = passing_network.get("highest_volume_distributor", "N/A")
        max_share = float(passing_network.get("max_player_pass_share_pct", 0.0))
        if max_share >= 15.0:
            simple_conclusions.append(
                f"🟡 **Time Dependente de {vol_player} e {hub_player}:** Sozinho, **{vol_player}** concentrou **{max_share}% de todos os passes do time**. "
                f"**Conclusão simples:** Toda a construção passa por eles; se o adversário colar um marcador neles, o time perde a saída de bola."
            )

        if not simple_conclusions:
            simple_conclusions.append(
                f"⚖️ **Jogo Equilibrado Dentro dos Padrões Normais:** O **{target_team}** manteve **{o_org['overall_pass_completion_pct']}%** de acerto de passes, "
                f"gerando **{o_org['total_xg']} xG** contra **{d_org['xg_conceded']} xG** sofridos."
            )

        return {
            "aerial_and_crossing_metrics": aerial,
            "plain_language_conclusions": simple_conclusions,
        }


class NumericHallucinationGuard:
    """
    Extrai recursivamente todos os números válidos presentes no dicionário de evidências
    e audita se um relatório textual contém percentuais ou decimais inventados.
    """

    @classmethod
    def extract_allowed_numbers(cls, data: Any) -> Set[str]:
        allowed: Set[str] = set()

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)
            elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
                val = float(obj)
                allowed.add(f"{val:.0f}")
                allowed.add(f"{val:.1f}")
                allowed.add(f"{val:.2f}")
                allowed.add(f"{val:.3f}")
                allowed.add(f"{val:.4f}")
                allowed.add(f"{val:.1f}".replace(".", ","))
                allowed.add(f"{val:.2f}".replace(".", ","))
                allowed.add(f"{val:.3f}".replace(".", ","))
                allowed.add(f"{val:.4f}".replace(".", ","))

        _walk(data)
        structural_constants = {
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "10.5", "10,5",
            "11", "12", "13", "14", "15", "16", "18", "20", "22", "25", "30",
            "45", "50", "60", "80", "90", "100", "120",
        }
        return allowed.union(structural_constants)

    @classmethod
    def audit_text_numbers(
        cls, text: str, evidence_bundle: Dict[str, Any]
    ) -> Dict[str, Any]:
        allowed = cls.extract_allowed_numbers(evidence_bundle)
        decimal_matches = re.findall(r"\b\d+[.,]\d+\b", text)

        unverified: List[str] = []
        verified_count = 0

        for num_str in decimal_matches:
            norm_dot = num_str.replace(",", ".")
            try:
                val = float(norm_dot)
                candidates = {
                    num_str,
                    norm_dot,
                    f"{val:.1f}",
                    f"{val:.2f}",
                    f"{val:.3f}",
                    f"{val:.4f}",
                }
                if candidates.intersection(allowed):
                    verified_count += 1
                else:
                    unverified.append(num_str)
            except ValueError:
                continue

        return {
            "is_grounded": len(unverified) == 0,
            "verified_decimals_count": verified_count,
            "unverified_decimals": unverified,
        }


class TacticalReportBuilder:
    """
    Construtor Mestre de Relatórios:
    1. Relatório da Partida (IA Gemini ou Determinístico + Conclusões Simples + Decisão Final).
    2. Relatório Exclusivo de Jogadores (Dossiê Individual e Comparativo).
    3. Relatório Histórico Multi-Jogos de um Mesmo Time.
    """

    @staticmethod
    def _build_player_specific_dossier(
        df_events: pd.DataFrame, target_player: str
    ) -> Dict[str, Any]:
        p_ev = df_events[df_events["player_name"] == target_player].copy()
        if p_ev.empty:
            return {"status": "NOT_FOUND", "player_name": target_player}

        team_name = str(p_ev["team_name"].iloc[0])
        pos_mode = p_ev["position_name"].dropna().mode()
        position = str(pos_mode.iloc[0]) if not pos_mode.empty else "Unknown"

        valid_xy = p_ev[p_ev["x"].notna() & p_ev["y"].notna()]
        avg_x = round(float(valid_xy["x"].mean()), 2) if not valid_xy.empty else 60.0
        avg_y = round(float(valid_xy["y"].mean()), 2) if not valid_xy.empty else 40.0

        dom_third = (
            str(valid_xy["origin_third"].mode().iloc[0])
            if ("origin_third" in valid_xy.columns and not valid_xy["origin_third"].dropna().empty)
            else "Terço Médio"
        )
        dom_corridor = (
            str(valid_xy["origin_corridor"].mode().iloc[0])
            if ("origin_corridor" in valid_xy.columns and not valid_xy["origin_corridor"].dropna().empty)
            else "Corredor Central"
        )

        passes = p_ev[p_ev["type_name"] == "Pass"]
        n_passes = int(len(passes))
        comp_passes = int(passes["is_pass_completed"].sum())
        pass_acc_pct = (
            round((comp_passes / n_passes) * 100.0, 2) if n_passes > 0 else 0.0
        )

        press_passes = passes[passes["under_pressure"] == 1]
        unpress_passes = passes[passes["under_pressure"] == 0]
        press_acc_pct = (
            round(
                (press_passes["is_pass_completed"].sum() / len(press_passes)) * 100.0,
                2,
            )
            if len(press_passes) > 0
            else 0.0
        )
        unpress_acc_pct = (
            round(
                (unpress_passes["is_pass_completed"].sum() / len(unpress_passes)) * 100.0,
                2,
            )
            if len(unpress_passes) > 0
            else 0.0
        )
        pressure_drop_pct = round(unpress_acc_pct - press_acc_pct, 2)

        team_passes_to_player = df_events[
            (df_events["team_name"] == team_name)
            & (df_events["type_name"] == "Pass")
            & (df_events["is_pass_completed"] == 1)
            & (df_events["pass_recipient_name"] == target_player)
        ]
        feeders = team_passes_to_player["player_name"].dropna().value_counts()
        top_feeder = (
            PlayerNameNormalizer.to_common_name(str(feeders.index[0]))
            if not feeders.empty
            else "Não identificado"
        )
        top_feeder_count = int(feeders.iloc[0]) if not feeders.empty else 0

        targets = (
            passes[passes["is_pass_completed"] == 1]["pass_recipient_name"]
            .dropna()
            .value_counts()
        )
        top_target = (
            PlayerNameNormalizer.to_common_name(str(targets.index[0]))
            if not targets.empty
            else "Não identificado"
        )
        top_target_count = int(targets.iloc[0]) if not targets.empty else 0

        prog_actions = int(p_ev["is_progressive_action"].sum())
        line_breaks = int(p_ev.get("is_line_breaking_pass", pd.Series(0)).sum())
        z14_entries = int(p_ev["is_zone_14_entry"].sum())
        box_entries = int(p_ev["is_box_entry"].sum())
        turnovers = int(p_ev["is_turnover"].sum())
        recoveries = int(p_ev["is_ball_recovery"].sum())
        shots = p_ev[p_ev["type_name"] == "Shot"]
        xg_val = round(float(shots["shot_statsbomb_xg"].fillna(0.0).sum()), 3)
        xt_val = round(
            float(p_ev[p_ev.get("delta_xt", pd.Series(0.0)) > 0]["delta_xt"].sum()),
            4,
        )

        return {
            "status": "OK",
            "player_name": PlayerNameNormalizer.to_common_name(target_player),
            "raw_player_name": target_player,
            "team_name": team_name,
            "position_name": position,
            "avg_x": avg_x,
            "avg_y": avg_y,
            "dominant_third": dom_third,
            "dominant_corridor": dom_corridor,
            "total_actions": int(len(p_ev)),
            "passes_attempted": n_passes,
            "passes_completed": comp_passes,
            "pass_accuracy_pct": pass_acc_pct,
            "unpressured_pass_acc_pct": unpress_acc_pct,
            "pressured_pass_acc_pct": press_acc_pct,
            "accuracy_drop_under_pressure_pct": pressure_drop_pct,
            "primary_feeder_teammate": top_feeder,
            "passes_received_from_top_feeder": top_feeder_count,
            "primary_target_teammate": top_target,
            "passes_sent_to_top_target": top_target_count,
            "progressive_actions": prog_actions,
            "line_breaking_passes": line_breaks,
            "zone_14_entries": z14_entries,
            "box_entries": box_entries,
            "xt_generated": xt_val,
            "shots": int(len(shots)),
            "xg": xg_val,
            "turnovers": turnovers,
            "ball_recoveries": recoveries,
        }

    @classmethod
    def assemble_evidence_package(
        cls,
        df_events: pd.DataFrame,
        df_chains: pd.DataFrame,
        target_team: str,
        match_id: int = 0,
        user_query: str = "",
        classifier: Optional[PossessionDangerClassifier] = None,
        is_simulation: bool = False,
    ) -> Dict[str, Any]:
        opponents = [
            t for t in df_events["team_name"].dropna().unique() if t != target_team
        ]
        opponent_name = str(opponents[0]) if opponents else "Adversário"

        xt_df = ExpectedThreatModel.enrich_events_with_xt(df_events)
        all_players_in_match = (
            xt_df["player_name"].dropna().astype(str).unique().tolist()
        )

        matched_players = QueryIntentRouter.extract_target_players(
            user_query, all_players_in_match
        )
        role_players = []
        if not matched_players:
            role_players = QueryIntentRouter.resolve_role_based_players(
                user_query, xt_df, target_team=target_team, opponent_team=opponent_name
            )
            matched_players = role_players

        nlp_details = QueryIntentRouter.detect_focus_with_probabilities(
            user_query, all_players_in_match, role_resolved_players=role_players
        )
        focus_mode = nlp_details["predicted_intent"]

        focused_players_dossiers = [
            cls._build_player_specific_dossier(xt_df, p_name)
            for p_name in matched_players
        ]

        fases_summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
            xt_df, df_chains, target_team
        )
        net_res = PassingNetworkAnalyzer.build_pass_network(
            xt_df, target_team, until_first_sub=True
        )
        opp_net_res = PassingNetworkAnalyzer.build_pass_network(
            xt_df, opponent_name, until_first_sub=True
        )
        xt_summary = ExpectedThreatModel.compute_team_xt_summary(xt_df, target_team)
        cluster_turnovers = SpatialTacticalClustering.analyze_turnover_clusters(
            xt_df, target_team
        )
        cluster_recoveries = SpatialTacticalClustering.analyze_recovery_density_dbscan(
            xt_df, target_team
        )
        players_df = PlayerTacticalEvaluator.evaluate_team_players(xt_df, target_team)
        opp_players_df = PlayerTacticalEvaluator.evaluate_team_players(
            xt_df, opponent_name
        )
        subs_summary = PlayerTacticalEvaluator.recommend_tactical_substitutions(
            xt_df, target_team
        )
        diagnostics = TacticalDiagnosticEngine.generate_comprehensive_diagnostics(
            xt_df, df_chains, target_team, classifier=classifier
        )

        discrepancy_analysis = (
            BenchmarkDiscrepancyEngine.generate_plain_language_discrepancy_conclusions(
                df_events=xt_df,
                phases_metrics=fases_summary,
                passing_network=net_res["graph_metrics"],
                clustering_data=cluster_turnovers,
                target_team=target_team,
                opponent_team=opponent_name,
            )
        )

        ml_pred_summary: Dict[str, Any] = {"status": "NOT_AVAILABLE"}
        if classifier is None:
            classifier = PossessionDangerClassifier()
            classifier.load_models()
        if classifier.xgb_model is not None and not df_chains.empty:
            try:
                ml_pred_summary = classifier.predict_possession_probabilities(
                    df_chains, target_team=target_team
                )
            except Exception:
                ml_pred_summary = {"status": "SKIPPED"}

        return {
            "metadata": {
                "match_id": int(match_id),
                "target_team": target_team,
                "opponent_team": opponent_name,
                "is_simulation_data": bool(is_simulation),
                "total_events_analyzed": int(len(df_events)),
                "team_events_analyzed": int(
                    (df_events["team_name"] == target_team).sum()
                ),
                "user_query": user_query or "Análise Tática Completa",
                "detected_focus": focus_mode,
                "matched_players_in_query": [
                    PlayerNameNormalizer.to_common_name(p) for p in matched_players
                ],
                "nlp_model_used": nlp_details["interpreted_by"],
                "nlp_confidence_pct": nlp_details["confidence_pct"],
                "nlp_top_3_probabilities": nlp_details["top_3_intents"],
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "discrepancy_and_simple_conclusions": discrepancy_analysis,
            "focused_player_deep_dive": focused_players_dossiers,
            "phases_metrics": fases_summary,
            "passing_network": net_res["graph_metrics"],
            "opponent_passing_network": opp_net_res["graph_metrics"],
            "expected_threat_xt": xt_summary,
            "spatial_clustering": {
                "turnovers_kmeans": cluster_turnovers,
                "recoveries_dbscan": cluster_recoveries,
            },
            "supervised_ml_predictions": ml_pred_summary,
            "top_players": players_df.head(8).to_dict(orient="records")
            if not players_df.empty
            else [],
            "opponent_top_players": opp_players_df.head(5).to_dict(orient="records")
            if not opp_players_df.empty
            else [],
            "substitutions_analysis": subs_summary,
            "structured_diagnostics": diagnostics,
        }

    @classmethod
    def generate_ai_report(
        cls,
        df_events: pd.DataFrame,
        df_chains: pd.DataFrame,
        target_team: str,
        user_query: str,
        match_id: int = 0,
        classifier: Optional[PossessionDangerClassifier] = None,
        is_simulation: bool = False,
    ) -> str:
        """
        Une o motor de evidências matemáticas à IA Generativa Gemini 2.5 Flash,
        validando com o guardião anti-alucinação e fazendo fallback determinístico se necessário.
        """
        evidence = cls.assemble_evidence_package(
            df_events=df_events,
            df_chains=df_chains,
            target_team=target_team,
            match_id=match_id,
            user_query=user_query,
            classifier=classifier,
            is_simulation=is_simulation,
        )

        intencao_detectada = evidence["metadata"]["detected_focus"]
        confianca = evidence["metadata"]["nlp_confidence_pct"]
        print(f"🧠 [Rede Neural MLP] Intenção detectada: {intencao_detectada} (Confiança: {confianca}%)")

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                client = genai.Client(api_key=api_key)
                prompt = f"""
                Você é o Analista Tático Chefe do Tactical Intelligence Lab. 
                O usuário fez o seguinte comando/pergunta: "{user_query}"
                A nossa rede neural classificou o foco da intenção como: "{intencao_detectada}".
                
                Abaixo estão todas as evidências matemáticas, estatísticas e espaciais reais extraídas da partida pelos nossos algoritmos:
                {evidence}
                
                Instruções rígidas:
                - Redija um relatório tático executivo de alto nível técnico respondendo diretamente ao usuário.
                - Utilize exclusivamente os números, percentuais e dados contidos no dicionário de evidências.
                - É terminantemente proibido inventar estatísticas ou números que não constem nas evidências.
                """
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2)
                )
                
                report_text = response.text
                auditoria = NumericHallucinationGuard.audit_text_numbers(report_text, evidence)
                if auditoria["is_grounded"]:
                    print("✅ [Guardião Anti-Alucinação] Resposta 100% fundamentada nos dados reais!")
                else:
                    print(f"⚠️ [Guardião Anti-Alucinação] Alerta de números não verificados: {auditoria['unverified_decimals']}")
                
                return report_text

            except Exception as e:
                print(f"⚠️ Erro ao chamar a API do Gemini ({e}). Realizando fallback para o gerador determinístico.")

        print("⚙️ [Modo Determinístico] Gerando relatório estruturado padrão via código local.")
        return cls.build_deterministic_markdown_report(evidence)

    @classmethod
    def build_deterministic_markdown_report(
        cls, evidence: Dict[str, Any]
    ) -> str:
        """
        Gera o Relatório Completo com:
        - Resposta Direta à Pergunta (incluindo dossiê de jogador ou meia/volante adversário).
        - Resumo Simples em Linguagem Comum (Conclusões tiradas das discrepâncias dos dados).
        - Relatório Aprofundado (Todas as seções técnicas com os dados do jogo).
        - Resumo Final e Tomada de Decisão sobre a Pergunta.
        """
        meta = evidence["metadata"]
        team = meta["target_team"]
        opp = meta["opponent_team"]
        focus = meta["detected_focus"]
        user_q = meta["user_query"]
        is_sim = meta.get("is_simulation_data", False)

        disc = evidence.get("discrepancy_and_simple_conclusions", {})
        aerial = disc.get("aerial_and_crossing_metrics", {})
        simple_bullets = disc.get("plain_language_conclusions", [])

        pm = evidence["phases_metrics"]
        d_org = pm["defensive_organization"]
        o_org = pm["offensive_organization"]
        o_tr = pm["offensive_transition"]
        d_tr = pm["defensive_transition"]
        mid = pm["midfield_control"]
        sp = pm["set_pieces"]

        net = evidence["passing_network"]
        opp_net = evidence.get("opponent_passing_network", {})
        xt = evidence["expected_threat_xt"]
        km = evidence["spatial_clustering"]["turnovers_kmeans"]
        db = evidence["spatial_clustering"]["recoveries_dbscan"]
        ml = evidence["supervised_ml_predictions"]
        top_p = evidence["top_players"]
        opp_top_p = evidence.get("opponent_top_players", [])
        subs = evidence["substitutions_analysis"]
        diags = evidence["structured_diagnostics"]
        focused_dossiers = evidence.get("focused_player_deep_dive", [])

        lines: List[str] = []

        lines.append(
            f"# RELATÓRIO DE INTELIGÊNCIA TÁTICA E PRESCRIÇÃO ESTRATÉGICA — {team.upper()}"
        )
        if is_sim:
            lines.append(
                "> ⚠️ **Nota de Base de Dados:** Partida processada sob modelo estruturado do confronto para demonstração laboratorial."
            )
        lines.append(
            f"**Partida ID:** `{meta['match_id']}` | **Equipe Analisada:** {team} | **Adversário:** {opp}  "
        )
        lines.append(
            f"**Eventos Auditados:** {meta['total_events_analyzed']} ({meta['team_events_analyzed']} de {team}) | "
            f"**Foco Semântico Detectado:** `{focus}` (Confiança IA: **{meta.get('nlp_confidence_pct', 100.0)}%**)  "
        )
        lines.append(f"**Comando / Pergunta do Analista:** *\"{user_q}\"*  ")
        lines.append("---")

        # =====================================================================
        # BLOCO 1: RESPOSTA DIRETA BASEADA NOS DADOS DO JOGO
        # =====================================================================
        lines.append(f"## 🎯 RESPOSTA TÁTICA DIRETA: \"{user_q}\"")

        if focused_dossiers:
            for p in focused_dossiers:
                lines.append(
                    f"### Plano Tático Baseado nos Dados do Jogo para **{p['player_name']}** ({p['team_name']} — {p['position_name']})\n"
                    f"* **Onde ele joga de verdade em campo:** Sua posição média registrada nos eventos é **`({p['avg_x']}, {p['avg_y']})`**, atuando principalmente no **{p['dominant_third']}** pelo **{p['dominant_corridor']}** (participou de **{p['total_actions']} ações** na partida).\n"
                    f"* **Quem faz a bola chegar nele (Como cortar a origem):** O principal abastecedor dele é **{p['primary_feeder_teammate']}**, que entregou **{p['passes_received_from_top_feeder']} passes completos** para **{p['player_name']}**. Quando **{p['player_name']}** domina, seu alvo favorito de passe é **{p['primary_target_teammate']}** (**{p['passes_sent_to_top_target']} passes**).\n"
                    f"* **Como ele reage sob marcação apertada:** Livre de pressão, ele acerta **{p['unpressured_pass_acc_pct']}%** dos passes; quando recebe combate direto (`under_pressure`), sua precisão vai para **{p['pressured_pass_acc_pct']}%** (diferença de **{p['accuracy_drop_under_pressure_pct']}%**), tendo cometido **{p['turnovers']} perdas de posse**.\n"
                    f"* **Perigo real que ele gerou no jogo:** Somou **{p['progressive_actions']} avanços progressivos**, **{p['line_breaking_passes']} passes que quebraram linhas**, **{p['zone_14_entries']} bolas na entrada da área (Zona 14)**, **{p['box_entries']} bolas dentro da área**, **+{p['xt_generated']} xT** e **{p['xg']} xG** ({p['shots']} chutes).\n\n"
                    f"**🛠️ O que fazer na prática (Plano A e Plano B):**\n"
                    f"1. **Plano A (Cortar a Linha de Abastecimento):** Posicionar nosso volante/meia do setor fechando a linha de passe entre **{p['primary_feeder_teammate']}** e **{p['player_name']}** no **{p['dominant_corridor']}**, impedindo que a bola chegue limpa nele.\n"
                    f"2. **Plano B (Encaixe Curto de Costas):** Assim que **{p['player_name']}** receber no **{p['dominant_third']}**, dar bote em menos de 2 segundos para não deixá-lo girar de frente e forçar o passe pressionado (onde sua precisão cai para **{p['pressured_pass_acc_pct']}%**), vigiando a infiltração de **{p['primary_target_teammate']}**."
                )
            final_verdict_text = (
                f"Para responder à pergunta *\"{user_q}\"*, a decisão tática principal é **isolar {focused_dossiers[0]['player_name']} ({focused_dossiers[0]['team_name']}) bloqueando os passes que vêm de {focused_dossiers[0]['primary_feeder_teammate']} no {focused_dossiers[0]['dominant_corridor']}** e pressioná-lo de costas antes que acione **{focused_dossiers[0]['primary_target_teammate']}**."
            )

        elif focus in ("INDIVIDUAL_AND_COMPARISON", "PLAYER_SPECIFIC_TACTIC"):
            q_lower = user_q.lower()
            asks_opp = any(w in q_lower for w in ["adversario", "adversário", "deles", "oponente"])
            ref_list = opp_top_p if (asks_opp and opp_top_p) else top_p
            ref_team = opp if (asks_opp and opp_top_p) else team
            ref_net = opp_net if (asks_opp and opp_net) else net

            if ref_list:
                best_p = ref_list[0]
                pivot_name = ref_net.get("primary_bridge_player_betweenness", best_p["player_name"])
                lines.append(
                    f"Analisando os dados individuais de **{ref_team}**, o jogador-chave de criação e articulação é **{best_p['player_name']}** ({best_p['position_name']}, Score Tático = **{best_p['tactical_impact_score']}**) junto ao pivô de circulação **{pivot_name}** (Betweenness = **{ref_net.get('primary_bridge_score', 0.0)}**).\n\n"
                    f"* **Números de {best_p['player_name']} no jogo:** Acertou **{best_p['passes_completed']}/{best_p['passes_attempted']} passes ({best_p['pass_accuracy_pct']}%)**, com **{best_p['press_retention_pct']}%** de retenção sob pressão, **{best_p['progressive_actions']} ações progressivas**, **{best_p['line_breaking_passes']} quebras de linha**, **+{best_p['xt_generated']} xT** e **{best_p['turnovers']} perdas de posse**.\n"
                    f"* **Tática para Neutralizar / Explorar:** Fechar o espaço central/corredor onde **{best_p['player_name']}** e **{pivot_name}** tabelam ({ref_net.get('max_player_pass_share_pct', 0.0)}% de concentração de volume) e forçar a saída adversária pelas laterais sob pressão."
                )
                final_verdict_text = (
                    f"A decisão final para *\"{user_q}\"* é **encaixar marcação em {best_p['player_name']} e fechar a linha de passe do pivô {pivot_name}**, que concentram a criação de {ref_team}."
                )
            else:
                final_verdict_text = f"Concentrar a marcação no setor central e explorar o {o_org['preferred_attack_corridor']}."

        elif focus == "DEFENSIVE_VULNERABILITIES":
            vuln_sec = d_org["most_vulnerable_defensive_sector"]
            v_info = d_org["corridor_vulnerability_breakdown"].get(vuln_sec, {})
            lines.append(
                f"Pelos dados do jogo, o ponto mais vulnerável da defesa de **{team}** é o **{vuln_sec}**, que cedeu **{v_info.get('progressive_actions_conceded', 0)} avanços progressivos ({v_info.get('share_of_opponent_progression_pct', 0.0)}%)** e **{v_info.get('box_entries_conceded', 0)} entradas na grande área**.\n"
                f"* Além disso, o adversário acertou **{d_org['switches_completed_by_opponent']} de {d_org['switches_faced']} inversões de lado ({d_org['switch_conceded_rate_pct']}%)** e entrou **{d_org['zone_14_entries_conceded']} vezes na Zona 14**.\n"
                f"* **Como explorar:** Atrair a marcação de um lado e virar rápido o jogo para atacar o **{vuln_sec}** ou infiltrar pelo meio na entrada da área."
            )
            final_verdict_text = (
                f"A decisão final sobre a defesa de **{team}** é **atacar prioritariamente o {vuln_sec}** (que concentrou {v_info.get('share_of_opponent_progression_pct', 0.0)}% dos avanços sofridos) usando inversões rápidas e infiltrações na Zona 14."
            )

        elif focus == "PRESSING_AND_BUILDUP":
            rc = km.get("highest_risk_exposure_cluster") or {}
            lines.append(
                f"Para travar a saída de bola de **{team}** (que tenta sair curto em **{o_org['short_buildup_ratio_pct']}%** das vezes no desenho **{net.get('inferred_positional_structure', 'N/A')}** e errou **{o_org['buildup_turnovers_in_own_third']} bolas** no campo de defesa):\n"
                f"1. **Travar o Pivô:** Colar um marcador em **{net.get('primary_bridge_player_betweenness', 'N/A')}** (Betweenness = **{net.get('primary_bridge_score', 0.0)}**) e em **{net.get('highest_volume_distributor', 'N/A')}** (**{net.get('max_player_pass_share_pct', 0.0)}%** dos passes).\n"
                f"2. **Empurrar para a Zona de Erro:** Forçar a bola a ir para o **{rc.get('tactical_third', 'Terço Defensivo')} ({rc.get('tactical_corridor', 'Lateral')})**, onde o time perde a bola em **{rc.get('turnover_rate_per_touch_pct', 0.0)}%** dos toques."
            )
            final_verdict_text = (
                f"Para pressionar a saída de bola de **{team}**, a decisão final é **bloquear o passe no pivô {net.get('primary_bridge_player_betweenness', 'N/A')} e forçar o passe para o {rc.get('tactical_corridor', 'corredor lateral')}**, onde a taxa de perda chega a {rc.get('turnover_rate_per_touch_pct', 0.0)}%."
            )

        else:
            vuln_sec = d_org["most_vulnerable_defensive_sector"]
            lines.append(
                f"Com base nos **{meta['total_events_analyzed']} eventos auditados**, **{team}** jogou no formato real **{net.get('inferred_positional_structure', 'N/A')}**, "
                f"tendo como principal arma o ataque pelo **{o_org['preferred_attack_corridor']}** (gerando **{o_org['total_xg']} xG** e **+{xt['total_xt_generated']} xT**), "
                f"mas apresentou vulnerabilidade defensiva clara no **{vuln_sec}**."
            )
            final_verdict_text = (
                f"A decisão estratégica final para **{team}** é **sustentar a criação pelo {o_org['preferred_attack_corridor']} com {net.get('primary_bridge_player_betweenness', 'N/A')}**, corrigindo urgentemente a cobertura defensiva no **{vuln_sec}**."
            )

        lines.append("---")

        # =====================================================================
        # BLOCO 2: RELATÓRIO SIMPLES EM LINGUAGEM COMUM (DISCREPÂNCIAS DOS DADOS)
        # =====================================================================
        lines.append(
            "## 💡 RESUMO SIMPLES EM LINGUAGEM COMUM (O QUE OS NÚMEROS FORA DO NORMAL MOSTRAM)"
        )
        lines.append(
            "*Abaixo estão as conclusões diretas tiradas exclusivamente dos dados que fugiram do padrão normal de uma partida:*"
        )
        for bullet in simple_bullets:
            lines.append(f"* {bullet}")

        lines.append(
            f"* **Resumo da Bola Aérea e Cruzamentos nos Dados:** **{team}** tentou **{aerial.get('crosses_attempted', 0)} cruzamentos** "
            f"({aerial.get('crosses_completed', 0)} certos, **{aerial.get('cross_accuracy_pct', 0.0)}%**), disputou **{aerial.get('aerial_duels_total', 0)} bolas pelo alto no ataque** "
            f"(ganhou **{aerial.get('aerial_duels_won', 0)}**, **{aerial.get('aerial_win_pct', 0.0)}%**) e finalizou **{aerial.get('headed_shots', 0)} vez(es) de cabeça** "
            f"(**{aerial.get('headed_goals', 0)} gol(s)**, **{aerial.get('headed_xg', 0.0)} xG**)."
        )
        lines.append("---")

        # =====================================================================
        # BLOCO 3: RELATÓRIO TÉCNICO APROFUNDADO (TODAS AS 13 SEÇÕES)
        # =====================================================================
        lines.append("## 1 & 2. IDENTIFICAÇÃO E RESUMO EXECUTIVO APROFUNDADO")
        lines.append(
            f"A equipe **{team}** estruturou-se em posse num desenho real **{net.get('inferred_positional_structure', 'N/A')}** "
            f"(analisado até os {net.get('analyzed_until_minute', 90.0)} min), apresentando **{o_org['overall_pass_completion_pct']}%** de precisão global "
            f"em **{o_org['total_passes']} passes**, gerando **+{xt['total_xt_generated']} xT** líquido e **{o_org['total_xg']} xG** em **{o_org['total_shots']} finalizações**. "
            f"Sem a bola, operou em **{d_org['block_profile']}** com **PPDA de {d_org['ppda']}** e altura média de engajamento defensivo em **{d_org['avg_defensive_engagement_height_m']} m**."
        )

        lines.append("\n## 3. DIAGNÓSTICO COLETIVO E TOPOLOGIA DA REDE")
        lines.append(
            f"* **Estrutura Posicional Real (Rede de Passes):** `{net.get('inferred_positional_structure', 'N/A')}` com densidade topológica de **{net.get('network_density', 0.0)}**, "
            f"reciprocidade de **{net.get('network_reciprocity', 0.0)}** e coeficiente de triangulação (*clustering*) de **{net.get('avg_clustering_coefficient', 0.0)}**.\n"
            f"* **Pivô da Construção (Maior Intermediação):** **{net.get('primary_bridge_player_betweenness', 'N/A')}** (*Betweenness* = **{net.get('primary_bridge_score', 0.0)}**).\n"
            f"* **Centro Gravitacional (Maior PageRank):** **{net.get('primary_gravity_playmaker_pagerank', 'N/A')}** (*PageRank* = **{net.get('primary_playmaker_pagerank_score', 0.0)}**).\n"
            f"* **Balanço Horizontal:** Centroide lateral em **Y = {net.get('team_weighted_centroid_y', 40.0)}** ({net.get('lateral_asymmetry_diagnosis', 'Equilibrado')})."
        )

        lines.append("\n## 4. ANÁLISE DETALHADA POR FASE DO JOGO")
        lines.append(
            f"### A. Organização Defensiva\n"
            f"* **Intensidade de Pressão (PPDA):** **{d_org['ppda']}** ({d_org['ppda_numerator_opp_passes']} passes adversários permitidos na construção / {d_org['ppda_denominator_def_actions']} ações defensivas altas).\n"
            f"* **Altura e Compactação das Ações Defensivas:** Altura média = **{d_org['avg_defensive_engagement_height_m']} m** | Dispersão longitudinal = **{d_org['longitudinal_dispersion_m']} m** | Dispersão lateral = **{d_org['lateral_dispersion_m']} m**.\n"
            f"* **Setor Defensivo Mais Vulnerável:** **{d_org['most_vulnerable_defensive_sector']}**.\n"
            f"* **Resposta a Inversões de Jogo:** O adversário completou **{d_org['switches_completed_by_opponent']} de {d_org['switches_faced']}** inversões longas (**{d_org['switch_conceded_rate_pct']}%**).\n"
            f"* **Proteção Entrelinhas e Área:** Cedeu **{d_org['zone_14_entries_conceded']} entradas na Zona 14**, **{d_org['deep_completions_conceded']} passes profundos (*Deep Completions*)** e **{d_org['xg_conceded']} xG** ({d_org['shots_conceded']} chutes)."
        )
        lines.append(
            f"### B. Organização Ofensiva e Jogo Aéreo\n"
            f"* **Saída de Bola (1º Terço):** **{o_org['short_buildup_ratio_pct']}%** de saída curta ({o_org['buildup_passes_count']} passes no terço defensivo, **{o_org['buildup_completion_pct']}%** de acerto e **{o_org['buildup_turnovers_in_own_third']} perdas de posse** no próprio terço).\n"
            f"* **Progressão e Corredor Preferencial:** **{o_org['total_progressive_actions']} ações progressivas**, priorizando o **{o_org['preferred_attack_corridor']}**.\n"
            f"* **Ocupação de Zonas Críticas:** **{o_org['zone_14_entries']} entradas na Zona 14**, **{o_org['offensive_half_space_actions']} ações nos meios-espaços ofensivos**, **{o_org['penalty_box_entries']} entradas na grande área** e **{o_org['deep_completions']} *deep completions***.\n"
            f"* **Cruzamentos e Bola Aérea Ofensiva:** **{aerial.get('crosses_attempted', 0)} cruzamentos** ({aerial.get('crosses_completed', 0)} certos, **{aerial.get('cross_accuracy_pct', 0.0)}%**) e **{aerial.get('aerial_duels_won', 0)}/{aerial.get('aerial_duels_total', 0)} duelos pelo alto ganhos ({aerial.get('aerial_win_pct', 0.0)}%)**."
        )
        lines.append(
            f"### C & D. Transições (Ofensiva e Defensiva)\n"
            f"* **Transição Ofensiva:** Velocidade direta média de **{o_tr['overall_direct_speed_m_s']} m/s** em {o_tr['total_possessions_analyzed']} posses. Executou **{o_tr['counter_attacks_count']} contra-ataques rápidos** (velocidade média de **{o_tr['counter_attack_avg_speed_m_s']} m/s**), com taxa de eficiência de **{o_tr['counter_efficiency_pct']}%**.\n"
            f"* **Transição Defensiva (*Gegenpressing* 5s):** Sofreu **{d_tr['turnovers_in_attacking_half']} perdas no campo de ataque**, reagindo com pressão imediata nos 5 segundos seguintes em **{d_tr['post_loss_5s_press_reaction_pct']}%** dos lances e recuperando a posse em 5s em **{d_tr['post_loss_5s_recovery_pct']}%**."
        )
        lines.append(
            f"### E & F. Meio-Campo e Bolas Paradas\n"
            f"* **Controle de Meio-Campo:** *Field Tilt* de **{mid['field_tilt_pct']}%**, posse no terço médio de **{mid['midfield_possession_share_pct']}%** e resistência à pressão de **{mid['press_resistance_completion_pct']}%**.\n"
            f"* **Bolas Paradas:** Cobrou **{sp['offensive_corners_count']} escanteios ofensivos** ({sp['offensive_corners_first_contact_won']} primeiros contatos ganhos, gerando **{sp['shots_generated_from_corners']} finalizações**) e defendeu **{sp['defensive_corners_faced']} escanteios**."
        )

        lines.append("\n## 5. RELATÓRIO DE JOGADORES (DESTAQUES DE AMBAS AS EQUIPES)")
        lines.append(f"### Destaques de {team}:")
        for p in top_p[:5]:
            lines.append(
                f"* **{p['player_name']}** ({p['position_name']}): Score Tático = **{p['tactical_impact_score']}** | "
                f"Passes = **{p['passes_completed']}/{p['passes_attempted']}** (**{p['pass_accuracy_pct']}%**) | "
                f"Ações Progressivas = **{p['progressive_actions']}** | Quebras de Linha = **{p['line_breaking_passes']}** | "
                f"xT Gerado = **+{p['xt_generated']}** | Recuperações = **{p['ball_recoveries']}** | Turnovers = **{p['turnovers']}**."
            )
        if opp_top_p:
            lines.append(f"\n### Principais Jogadores do Adversário ({opp}) para Monitorar:")
            for op in opp_top_p[:3]:
                lines.append(
                    f"* **{op['player_name']}** ({op['position_name']}): Score Tático = **{op['tactical_impact_score']}** | "
                    f"Passes = **{op['passes_completed']}/{op['passes_attempted']}** (**{op['pass_accuracy_pct']}%**) | "
                    f"Ações Progressivas = **{op['progressive_actions']}** | Quebras de Linha = **{op['line_breaking_passes']}** | "
                    f"xT Gerado = **+{op['xt_generated']}** | Turnovers = **{op['turnovers']}**."
                )

        lines.append("\n## 6, 7, 8 & 9. PADRÕES ESPACIAIS E EVIDÊNCIAS DE MACHINE LEARNING")
        if km.get("status") == "OK" and km.get("highest_risk_exposure_cluster"):
            rc = km["highest_risk_exposure_cluster"]
            vc = km["highest_volume_cluster"]
            lines.append(
                f"* **Clusterização K-Means de Perdas de Posse ($K={km['optimal_k']}$, Silhouette = {km['silhouette_score']}):**\n"
                f"  - *Maior Volume Bruto:* **{vc['tactical_third']} ({vc['tactical_corridor']})**, com **{vc['turnovers_in_cluster']} perdas** (**{vc['share_of_total_turnovers_pct']}%** do total).\n"
                f"  - *Maior Vulnerabilidade Ajustada por Exposição:* **{rc['tactical_third']} ({rc['tactical_corridor']})**, com taxa de erro de **{rc['turnover_rate_per_touch_pct']}% por toque**."
            )
        if db.get("dense_zones_found", 0) > 0:
            t0 = db["pressing_traps"][0]
            lines.append(
                f"* **DBSCAN (Zonas de Armadilha de Pressão / Recuperação):** Detectados **{db['dense_zones_found']} núcleos densos**. Principal núcleo no **{t0['tactical_third']} ({t0['tactical_corridor']})** com **{t0['recoveries_count']} recuperações**."
            )
        if ml.get("status") == "OK":
            lines.append(
                f"* **Modelo Supervisionado XGBoost (Probabilidade de Perigo por Posse):** Probabilidade média esperada de perigo = **{ml['avg_predicted_danger_prob_pct']}%** (taxa real = **{ml['actual_danger_rate_pct']}%**)."
            )

        lines.append("\n## 10 & 11. DIAGNÓSTICOS CAUSA-EFEITO E PRESCRIÇÃO DE SUBSTITUIÇÕES")
        for idx, d in enumerate(diags, 1):
            lines.append(
                f"### Diagnóstico {idx}: {d['problem_title']} [Evidência: `{d['evidence_strength']}` | N={d['sample_size']}]\n"
                f"* **Explicação:** {d['tactical_interpretation']}\n"
                f"* **Plano A:** {d['recommendation_plan_a']} | **Plano B:** {d['recommendation_alternative_b']}"
            )

        if subs["recommended_substitutions"]:
            for s in subs["recommended_substitutions"]:
                lines.append(
                    f"* **Substituição Recomendada — Saída de {s['candidate_out']} ({s['position']})** [Prioridade: **{s['priority_score']}**]: {' '.join(s['tactical_reasons'])} -> *Entrada recomendada:* {s['ideal_replacement_profile']}"
                )

        # =====================================================================
        # BLOCO 4: RESUMO DO QUE FOI FALADO E DECISÃO FINAL SOBRE A PERGUNTA
        # =====================================================================
        lines.append("\n---")
        lines.append(
            "## 🏁 12 & 13. RESUMO DO QUE FOI FALADO E DECISÃO FINAL SOBRE A PERGUNTA"
        )
        lines.append(
            f"1. **Síntese Geral do Jogo:** O **{team}** atuou em `{net.get('inferred_positional_structure', 'N/A')}`, tendo **{net.get('primary_bridge_player_betweenness', 'N/A')}** como pivô da saída de bola, atacando principalmente pelo **{o_org['preferred_attack_corridor']}** (**{o_org['total_xg']} xG** criados) e sofrendo defensivamente no **{d_org['most_vulnerable_defensive_sector']}** (**{d_org['xg_conceded']} xG** cedidos).\n"
            f"2. **O Que Fugiu do Padrão Normal (Discrepância Principal):** {simple_bullets[0] if simple_bullets else 'Equilíbrio territorial.'}\n"
            f"3. **DECISÃO FINAL DA COMISSÃO TÉCNICA PARA A SUA PERGUNTA (*\"{user_q}\"*):**\n"
            f"   > **{final_verdict_text}**\n"
            f"4. **Nota de Transparência Científica:** {subs['data_limitations_notice']}"
        )

        return "\n".join(lines)

    @classmethod
    def build_multi_match_team_history_report(
        cls, trend_report: Dict[str, Any]
    ) -> str:
        if trend_report.get("status") != "OK":
            return "Não há partidas suficientes carregadas para este time."

        team = trend_report["team_name"]
        n_m = trend_report["matches_analyzed"]
        stats = trend_report["longitudinal_stability_stats"]
        diags = trend_report["pattern_diagnostics"]
        table = trend_report["per_match_table"]

        lines = [
            f"# 📚 DOSSIÊ HISTÓRICO MULTI-JOGOS DA EQUIPE — {team.upper()} ({n_m} PARTIDAS AUDITADAS)",
            f"**Base de Dados Consolidada:** Análise longitudinal de **{n_m} jogos** de **{team}** para identificar o DNA tático real da equipe.",
            "---",
            "## 1. PARTIDAS ANALISADAS NO HISTÓRICO DO TIME",
        ]
        for row in table:
            lines.append(
                f"* **Partida `{row['match_id']}` (vs {row['opponent']}):** PPDA = **{row['ppda']}** | Altura da Defesa = **{row['def_height_m']} m** | "
                f"Entradas Zona 14 = **{row['zone_14_entries']}** | Entradas na Área = **{row['box_entries']}** | "
                f"xG Criado = **{row['xg_created']}** vs xG Sofrido = **{row['xg_conceded']}** | "
                f"Setor Defensivo Mais Exposto = **{row['most_vulnerable_def_sector']}**."
            )

        lines.append("\n## 2. O QUE É PADRÃO RECORRENTE (CRÔNICO) VS. O QUE FOI JOGO ISOLADO")
        for d in diags:
            badge = (
                "🔴 PADRÃO CRÔNICO RECORRENTE"
                if "CRÔNICO" in d["classification"]
                else (
                    "🟡 TENDÊNCIA INTERMITENTE"
                    if "INTERMITENTE" in d["classification"]
                    else "⚪ ACONTECIMENTO ISOLADO"
                )
            )
            lines.append(
                f"* **{badge} — {d['pattern_type']} ({d['recurrence_rate_pct']}% dos jogos):** {d['tactical_explanation']}"
            )

        lines.append("\n## 3. MÉDIAS HISTÓRICAS E ESTABILIDADE DO MODELO DE JOGO")
        lines.append(
            f"* **Pressão Defensiva (PPDA Médio):** **{stats['ppda']['mean']}** (±{stats['ppda']['std']})  \n"
            f"* **Altura Média da Linha Defensiva:** **{stats['def_height_m']['mean']} m**  \n"
            f"* **Saída de Bola Curta Média:** **{stats['short_buildup_pct']['mean']}%** | **Resistência à Pressão:** **{stats['press_resistance_pct']['mean']}%**  \n"
            f"* **Produção Ofensiva Média por Jogo:** **{stats['zone_14_entries']['mean']} entradas na Zona 14**, **{stats['box_entries']['mean']} entradas na grande área** e **{stats['xg_created']['mean']} xG criado**."
        )

        chronic_vulns = [
            d for d in diags if "CRÔNICO" in d["classification"] or d["recurrence_rate_pct"] >= 60.0
        ]
        verdict = (
            chronic_vulns[0]["tactical_explanation"]
            if chronic_vulns
            else f"O {team} mantém média de {stats['xg_created']['mean']} xG por jogo e altura defensiva de {stats['def_height_m']['mean']} m."
        )

        lines.append("\n---")
        lines.append("## 🏁 CONCLUSÃO E DECISÃO FINAL DO HISTÓRICO DO TIME")
        lines.append(
            f"> **Veredito Baseado em {n_m} Jogos de {team}:** O comportamento estrutural que se repete de verdade ao longo dos jogos é: **{verdict}** Planeje o treino e a estratégia de jogo em cima desse padrão recorrente, e não de lances isolados de uma única partida."
        )
        return "\n".join(lines)

    @classmethod
    def build_dedicated_player_scouting_report(
        cls, df_events: pd.DataFrame, player_name: str
    ) -> str:
        xt_df = ExpectedThreatModel.enrich_events_with_xt(df_events)
        d = cls._build_player_specific_dossier(xt_df, player_name)
        if d.get("status") != "OK":
            return f"Jogador '{player_name}' não encontrado nos eventos desta partida."

        team_players = PlayerTacticalEvaluator.evaluate_team_players(
            xt_df, d["team_name"]
        )
        p_row = team_players[team_players["player_name"] == d["player_name"]]
        impact_score = (
            float(p_row["tactical_impact_score"].iloc[0]) if not p_row.empty else 0.0
        )
        early_acc = (
            float(p_row["pass_acc_0_60_pct"].iloc[0])
            if not p_row.empty
            else d["pass_accuracy_pct"]
        )
        late_acc = (
            float(p_row["pass_acc_60_plus_pct"].iloc[0])
            if not p_row.empty
            else d["pass_accuracy_pct"]
        )

        return (
            f"# 🏃 RELATÓRIO INDIVIDUAL DE JOGADOR (SCOUT & TÁTICA) — {d['player_name'].upper()}\n"
            f"**Clube/Seleção:** {d['team_name']} | **Posição em Campo:** {d['position_name']} | **Score de Impacto Tático:** `{impact_score}`\n"
            f"---\n"
            f"## 1. ONDE ELE JOGA E COMO PARTICIPA (MAPA ESPACIAL)\n"
            f"* **Posição Média (Centroide):** `({d['avg_x']}, {d['avg_y']})` — atua predominantemente no **{d['dominant_third']}** pelo **{d['dominant_corridor']}**.\n"
            f"* **Volume de Participação:** **{d['total_actions']} ações totais** na partida.\n"
            f"* **Conexões Preferenciais:** Recebeu mais bolas de **{d['primary_feeder_teammate']}** (**{d['passes_received_from_top_feeder']} passes**) e procurou principalmente **{d['primary_target_teammate']}** (**{d['passes_sent_to_top_target']} passes**).\n\n"
            f"## 2. EFICIÊNCIA TÉCNICA, CRIAÇÃO E RESISTÊNCIA À PRESSÃO\n"
            f"* **Passes Totais:** **{d['passes_completed']} certos em {d['passes_attempted']} tentados ({d['pass_accuracy_pct']}%)**.\n"
            f"* **Comportamento sob Pressão:** Livre de marcação acerta **{d['unpressured_pass_acc_pct']}%**; sob pressão direta acerta **{d['pressured_pass_acc_pct']}%** (variação de **{d['accuracy_drop_under_pressure_pct']}%**).\n"
            f"* **Rendimento 1º Tempo vs Final do Jogo (>60 min):** Precisão de **{early_acc}%** (0–60 min) vs **{late_acc}%** (pós-60 min).\n"
            f"* **Quebra de Linhas e Ameaça Criada:** **{d['progressive_actions']} avanços progressivos**, **{d['line_breaking_passes']} passes quebra-linhas**, **{d['zone_14_entries']} entradas na Zona 14**, **{d['box_entries']} bolas na grande área**, **+{d['xt_generated']} xT** e **{d['xg']} xG** em **{d['shots']} finalizações**.\n"
            f"* **Defesa e Segurança de Posse:** Recuperou **{d['ball_recoveries']} bolas** e sofreu **{d['turnovers']} perdas de posse (turnovers)**.\n\n"
            f"---\n"
            f"## 🏁 DECISÃO FINAL SOBRE {d['player_name'].upper()}\n"
            f"* **Se for do seu time (Como potencializar):** Fazer a bola chegar limpa nele através de **{d['primary_feeder_teammate']}** no **{d['dominant_corridor']}**, aproximando **{d['primary_target_teammate']}** para tabelar.\n"
            f"* **Se for adversário (Como anular):** Fechar a linha de passe que sai de **{d['primary_feeder_teammate']}** e dar bote imediato assim que **{d['player_name']}** receber de costas (forçando sua precisão a cair para **{d['pressured_pass_acc_pct']}%**)."
        )

    @staticmethod
    def export_report_files(
        markdown_text: str, output_prefix: str = "data/processed/relatorio_tatico"
    ) -> Dict[str, str]:
        md_path = Path(f"{output_prefix}.md")
        html_path = Path(f"{output_prefix}.html")
        md_path.parent.mkdir(parents=True, exist_ok=True)

        md_path.write_text(markdown_text, encoding="utf-8")

        body_html = (
            markdown_text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        body_html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", body_html, flags=re.MULTILINE)
        body_html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", body_html, flags=re.MULTILINE)
        body_html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", body_html, flags=re.MULTILINE)
        body_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body_html)
        body_html = re.sub(r"`(.+?)`", r"<code>\1</code>", body_html)
        body_html = body_html.replace("\n", "<br>\n")

        html_doc = f"""<!DOCTYPE html>

        @classmethod
    def generate_ai_report(
        cls,
        df_events: pd.DataFrame,
        df_chains: pd.DataFrame,
        target_team: str,
        user_query: str = "",
        match_id: int = 0,
        is_simulation: bool = False,
        prefer_llm: bool = True,
    ) -> str:
        from src.intelligence.llm_analyst import GenerativeTacticalAnalyst

        evidence_pkg = cls.assemble_evidence_package(
            df_events=df_events,
            df_chains=df_chains,
            target_team=target_team,
            match_id=match_id,
            user_query=user_query,
            is_simulation=is_simulation,
        )
        analyst = GenerativeTacticalAnalyst()
        res = analyst.generate_tactical_report(evidence_pkg, prefer_llm=prefer_llm)
        return str(res.get("report_markdown", ""))
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Relatório Tático - Tactical Intelligence Lab</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 980px; margin: 30px auto; padding: 25px; background: #f8fafc; }}
  .card {{ background: #ffffff; padding: 32px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
  h1 {{ color: #0f172a; border-bottom: 3px solid #2563eb; padding-bottom: 10px; }}
  h2 {{ color: #1d4ed8; margin-top: 28px; border-bottom: 1px solid #cbd5e1; padding-bottom: 6px; }}
  h3 {{ color: #0f172a; margin-top: 18px; }}
  code {{ background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-weight: bold; }}
</style>
</head>
<body>
<div class="card">
{body_html}
</div>
</body>
</html>"""
        html_path.write_text(html_doc, encoding="utf-8")

        return {"markdown_path": str(md_path), "html_path": str(html_path)}