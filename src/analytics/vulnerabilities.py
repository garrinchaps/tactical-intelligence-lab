"""
Onde atacar o adversário (e onde nós sofremos) — rodada 7.

Procura problemas REAIS e repetidos nos últimos jogos do time, com números da fonte, por SETOR e por JOGADOR:
  1. lateral/zagueiro/volante que é muito driblado ou desarma pouco (contra jogadores da mesma função);
  2. setor que perde duelos (no chão e no alto);
  3. volante que desarma pouco + time que deixa chutar de fora da área;
  4. muitos cruzamentos cedidos + zagueiros que perdem o jogo aéreo;
  5. bola nas costas / contra-ataque: perigo cedido em transição (chutes "fast break" do rival);
  6. saída de bola sob pressão: zagueiros e goleiro que perdem a bola ou erram passe;
  7. ponta/meia/centroavante que quase não defende (ações defensivas por 90 baixas e, onde a liga mede, distância);
  8. zagueiro BAIXO (Transfermarkt) contra os nossos atacantes altos — bola aérea direcionada nele;
  9. setor/corredor por onde o rival mais sofre chutes (mapa de chutes cedidos).
Cada achado: título, setor, lado, jogador (se houver), evidência numérica, gravidade (0–100), como explorar, amostra.

Regras honestas: só vira achado o que aparece com amostra mínima (≥ 3 jogos/≥ 180 min por jogador) e foge da
referência (percentil da mesma função ou média das competições). Sem tracking: "costas", "entre linhas" e
"pressão" são inferidos de números de bola (chutes em contra-ataque, perdas, passes) — dito em cada achado.
"""

from __future__ import annotations

from src.data_hub.gender import comp_sql
import json
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

SECTOR_OF = {"GK": "gol", "CB": "defesa", "LB": "defesa", "RB": "defesa", "LWB": "defesa", "RWB": "defesa", "DM": "meio",
             "CM": "meio", "AM": "meio", "LM": "meio", "RM": "meio", "LW": "ataque", "RW": "ataque", "ST": "ataque"}
SIDE_OF = {"LB": "esquerda", "LWB": "esquerda", "LM": "esquerda", "LW": "esquerda", "RB": "direita", "RWB": "direita",
           "RM": "direita", "RW": "direita"}
ROLE_PT = {"GK": "goleiro", "CB": "zagueiro", "LB": "lateral-esquerdo", "RB": "lateral-direito", "LWB": "ala esquerdo",
           "RWB": "ala direito", "DM": "volante", "CM": "meio-campista", "AM": "meia", "LM": "meia pela esquerda",
           "RM": "meia pela direita", "LW": "ponta-esquerda", "RW": "ponta-direita", "ST": "centroavante"}


def _recent_ids(db, names: Sequence[str], n: int) -> List[int]:
    ph = ",".join("?" * len(names))
    # só jogos com MINUTOS por jogador (FotMob): a ESPN não informa minutos, e sem minutos não existe "por 90"
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT s.match_id, m.match_date FROM match_player_stats s JOIN matches m ON m.match_id = s.match_id "
            f"WHERE s.team_name IN ({ph}) AND (m.data_source = 'fotmob' OR s.minutes IS NOT NULL){comp_sql(names, 'm')} "
            f"ORDER BY m.match_date DESC LIMIT ?", list(names) + [int(n)]).fetchall()
    return [int(r[0]) for r in rows]


def _player_season(db, ids: List[int], names: Sequence[str]) -> pd.DataFrame:
    """Uma linha por jogador: soma dos números (por 90 só nos jogos em que cada número existe) + função mais usada."""
    from src.squad.positions import classify
    from src.data_hub.registry import source_from_internal_id

    if not ids:
        return pd.DataFrame()
    ph = ",".join("?" * len(ids))
    th = ",".join("?" * len(names))
    with db.connect() as conn:
        ps = pd.read_sql_query(f"SELECT match_id, player_name, minutes, stats_json FROM match_player_stats "
                               f"WHERE match_id IN ({ph}) AND team_name IN ({th})", conn, params=ids + list(names))
        lu = pd.read_sql_query(f"SELECT match_id, player_name, position, is_starter FROM match_lineups "
                               f"WHERE match_id IN ({ph}) AND team_name IN ({th})", conn, params=ids + list(names))
    roles: Dict[str, Dict[str, int]] = {}
    starts: Dict[str, int] = {}
    for r in lu.itertuples():
        role, ok = classify(r.position, source_from_internal_id(int(r.match_id)))
        if ok and r.is_starter:
            roles.setdefault(r.player_name, {})
            roles[r.player_name][role] = roles[r.player_name].get(role, 0) + 1
            starts[r.player_name] = starts.get(r.player_name, 0) + 1
    out = []
    for name, g in ps.groupby("player_name"):
        tot: Dict[str, float] = {}
        mk: Dict[str, float] = {}
        mins = games = 0.0
        for js in g["stats_json"]:
            try:
                s = json.loads(js or "{}")
            except Exception:
                continue
            m = float(s.get("minutes") or 0)
            if m <= 0:
                continue
            mins += m
            games += 1
            for k, v in s.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("minutes", "fotmob_id"):
                    tot[k] = tot.get(k, 0.0) + float(v)
                    mk[k] = mk.get(k, 0.0) + m
        if games < 3 or mins < 180:
            continue
        rl = roles.get(name) or {}
        role = max(rl, key=rl.get) if rl else None
        row = {"jogador": name, "papel": role, "jogos": int(games), "minutos": int(mins), "titular": starts.get(name, 0)}
        for k, v in tot.items():
            row[k + "_90"] = v * 90 / mk[k] if mk.get(k) else None
            row[k + "_tot"] = v
        out.append(row)
    return pd.DataFrame(out)


def _pct(v: float, ref: pd.Series) -> Optional[float]:
    ref = pd.to_numeric(ref, errors="coerce").dropna()
    if v is None or pd.isna(v) or len(ref) < 15:
        return None
    return float(100.0 * ((ref < v).sum() + 0.5 * (ref == v).sum()) / len(ref))


def _ref_by_role(db=None) -> Dict[str, pd.DataFrame]:
    """Régua por função (a mesma da nota por estatísticas): indicadores por 90 de outras atuações.
    Se o arquivo da régua ainda não existe (ex.: versão nova da nota), monta uma vez e guarda."""
    from src.analytics import rating_box as RB

    ref = RB.reference()
    if ref.empty and db is not None:
        try:
            RB.build_reference(db, 600)
            ref = RB.reference()
        except Exception:
            ref = pd.DataFrame()
    if ref.empty:
        return {}
    return {f: g for f, g in ref.groupby("funcao")}


FUNC_OF = {"GK": "goleiro", "CB": "zagueiro", "LB": "lateral", "RB": "lateral", "LWB": "lateral", "RWB": "lateral",
           "DM": "volante", "CM": "meia central", "AM": "meia ofensivo", "LM": "ponta", "RM": "ponta", "LW": "ponta",
           "RW": "ponta", "ST": "centroavante"}


def team_vulnerabilities(db, names: Sequence[str], n: int = 12, our_names: Optional[Sequence[str]] = None,
                         heights: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    ids = _recent_ids(db, names, n)
    P = _player_season(db, ids, names)
    refs = _ref_by_role(db)
    out: List[Dict[str, Any]] = []

    def add(titulo, setor, lado, jogador, evid, grav, explorar, base):
        out.append({"titulo": titulo, "setor": setor, "lado": lado, "jogador": jogador, "evidencia": evid,
                    "gravidade": int(max(0, min(100, grav))), "explorar": explorar, "base": base})

    def regular(df):
        return df[df["titular"] >= max(2, int(0.4 * len(ids)))] if not df.empty else df

    # ---- jogadores, contra a mesma função
    if not P.empty:
        R = regular(P)
        for r in R.to_dict("records"):
            role = r.get("papel")
            fun = FUNC_OF.get(role or "")
            ref = refs.get(fun) if fun else None
            nome, setor, lado = r["jogador"], SECTOR_OF.get(role or "", ""), SIDE_OF.get(role or "")
            base = f"{r['jogos']} jogos, {r['minutos']} min"
            if ref is None:
                continue
            dp = r.get("dribbled_past_90")
            p_dp = _pct(dp, ref.get("driblado90", pd.Series(dtype=float)))
            if role in ("LB", "RB", "LWB", "RWB", "CB", "DM") and p_dp is not None and p_dp >= 80:
                add(f"{nome} é muito driblado", setor, lado, nome,
                    f"{dp:.2f} vezes driblado por 90 — mais que {p_dp:.0f}% dos {fun}s", p_dp,
                    f"Colocar o nosso melhor driblador no 1x1 contra ele{(' pela ' + lado) if lado else ''}; isolar o lado "
                    "com inversão rápida para chegar com ele de frente.", base)
            tk = r.get("matchstats.headers.tackles_90")
            p_tk = _pct(tk, ref.get("desarmes_ganhos90", pd.Series(dtype=float)))
            if role in ("DM", "CB", "LB", "RB") and p_tk is not None and p_tk <= 20:
                add(f"{nome} desarma pouco", setor, lado, nome,
                    f"{tk:.2f} desarmes por 90 — abaixo de {100 - p_tk:.0f}% dos {fun}s", 100 - p_tk,
                    ("Atrair a marcação dele e jogar no espaço às costas: o volante não corta a jogada, a bola chega limpa "
                     "na entrada da área." if role == "DM" else
                     f"Atacar com condução e tabelas{(' pela ' + lado) if lado else ''}: ele acompanha, mas não rouba."), base)
            aw, at = r.get("aerials_won_tot"), r.get("aerials_won_total_tot")
            if role in ("CB",) and aw is not None and at and at >= 8:
                rate = 100 * aw / at
                if rate < 45:
                    add(f"{nome} perde o jogo aéreo", "defesa", None, nome,
                        f"ganhou só {rate:.0f}% dos duelos aéreos ({aw:.0f} de {at:.0f})", 70 + (45 - rate),
                        "Cruzamentos e bolas longas direcionados na zona dele; escanteios no setor que ele marca.", base)
            dw, dl = r.get("duel_won_tot"), r.get("duel_lost_tot")
            if dw is not None and dl is not None and (dw + dl) >= 25:
                rate = 100 * dw / (dw + dl)
                if rate < 42 and role in ("CB", "LB", "RB", "DM", "CM"):
                    add(f"{nome} perde muitos duelos", setor, lado, nome, f"ganhou {rate:.0f}% dos {dw + dl:.0f} duelos",
                        60 + (42 - rate) * 2, "Forçar o duelo com ele: segunda bola e pressão no domínio.", base)
            if role in ("LW", "RW", "AM", "ST", "LM", "RM"):
                da = sum(float(r.get(k) or 0) for k in ("matchstats.headers.tackles_90", "interceptions_90", "recoveries_90"))
                refsum = (ref.get("desarmes_ganhos90", 0) + ref.get("intercept90", 0) + ref.get("recup90", 0)) \
                    if all(c in ref for c in ("desarmes_ganhos90", "intercept90", "recup90")) else None
                p_da = _pct(da, refsum) if refsum is not None else None
                km = r.get("distance_m_90")
                if p_da is not None and p_da <= 20:
                    extra = f" e corre {km / 1000:.1f} km por 90 (dado físico da liga)" if km else ""
                    add(f"{nome} quase não defende", setor, lado, nome,
                        f"{da:.2f} desarmes + interceptações + recuperações por 90 — abaixo de {100 - p_da:.0f}% dos {fun}s{extra}",
                        90 - p_da, f"Construir {('pela ' + lado + ' dele') if lado else 'pelo setor dele'}: o lateral/volante "
                                   "atrás dele fica em inferioridade quando ele não volta.", base)
            if role in ("CB", "GK"):
                ds = r.get("dispossessed_90")
                ap, att = r.get("accurate_passes_tot"), r.get("accurate_passes_total_tot")
                acc = 100 * ap / att if ap is not None and att else None
                if (acc is not None and acc < (70 if role == "GK" else 80)) or (ds is not None and ds >= 0.8):
                    bits = []
                    if acc is not None:
                        bits.append(f"acerta {acc:.0f}% dos passes")
                    if ds is not None and ds >= 0.8:
                        bits.append(f"perde a bola {ds:.2f} vezes por 90")
                    add(f"Saída de bola frágil: {nome} ({ROLE_PT.get(role, role)})", "defesa" if role == "CB" else "gol", None,
                        nome, " e ".join(bits), 55 + (80 - (acc or 80)),
                        "Pressão alta nele quando receber do goleiro/zagueiro; fechar o passe curto e forçar o chutão.",
                        base + " · pressão inferida pelos números de passe/perda, sem tracking")
    # ---- time: chutes cedidos (FotMob) por situação e zona
    if ids:
        ph = ",".join("?" * len(ids))
        th = ",".join("?" * len(names))
        with db.connect() as conn:
            try:
                sh = pd.read_sql_query(f"SELECT match_id, team_name, x, y, xg, situation, outcome FROM match_shots "
                                       f"WHERE match_id IN ({ph}) AND team_name NOT IN ({th})", conn, params=ids + list(names))
            except Exception:
                sh = pd.DataFrame()
            ts = pd.read_sql_query(f"SELECT match_id, team_name, stat_key, value FROM match_team_stats WHERE match_id IN ({ph})",
                                   conn, params=ids)
        g = sh["match_id"].nunique() if not sh.empty else 0
        if g >= 3:
            fb = sh[sh["situation"].isin(["FastBreak"])]
            if len(fb) >= 3 or (fb["xg"].sum() if len(fb) else 0) >= 0.8:
                add("Sofre em contra-ataque (bola nas costas)", "defesa", None, None,
                    f"{len(fb)} finalizações do rival em contra-ataque (xG {fb['xg'].sum():.2f}) em {g} jogos",
                    40 + 15 * fb["xg"].sum(), "Recuperar e acelerar: passe vertical logo após o desarme para atacar a linha "
                    "adiantada antes de ela recompor.", f"{g} jogos · inferido dos chutes, sem tracking")
            out_box = sh[sh["x"] < 102]
            if len(sh) and len(out_box) / len(sh) >= 0.45 and len(out_box) >= 10:
                add("Deixa chutar de fora da área", "meio", None, None,
                    f"{len(out_box)} de {len(sh)} chutes cedidos foram de fora da área ({100 * len(out_box) / len(sh):.0f}%)",
                    55 + (len(out_box) / len(sh) - 0.45) * 100, "Meias que chutam de média distância recebendo na entrada da "
                    "área: o volante deles não encurta.", f"{g} jogos")
            for lado, cond in (("esquerda", sh["y"] < 26.7), ("direita", sh["y"] > 53.3)):
                part = sh[cond & (sh["x"] >= 90)]
                if len(sh) >= 15 and len(part) / len(sh) >= 0.30:
                    add(f"Sofre muitos chutes pelo lado {lado} do ataque rival", "defesa",
                        "direita" if lado == "esquerda" else "esquerda", None,
                        f"{len(part)} dos {len(sh)} chutes cedidos ({100 * len(part) / len(sh):.0f}%) nasceram desse corredor "
                        f"(xG {part['xg'].sum():.2f})", 50 + (len(part) / len(sh) - 0.30) * 150,
                        f"Concentrar o ataque por esse lado: a defesa deles cede mais por ali.", f"{g} jogos")
        if not ts.empty:
            opp = ts[~ts["team_name"].isin(list(names))]
            cr = opp[opp["stat_key"] == "crosses_total"]
            if cr["match_id"].nunique() >= 3:
                crm = pd.to_numeric(cr["value"], errors="coerce").mean()
                if crm >= 18:
                    weak = [x for x in out if "perde o jogo aéreo" in x["titulo"]]
                    add("Cede muitos cruzamentos", "defesa", None, None,
                        f"o rival cruza {crm:.1f} vezes por jogo contra eles" + (f"; e {weak[0]['jogador']} perde o jogo aéreo"
                                                                                  if weak else ""),
                        45 + (crm - 18) * 2 + (15 if weak else 0), "Atacar pelos lados e cruzar — principalmente no segundo pau.",
                        f"{cr['match_id'].nunique()} jogos")
    # ---- altura: nosso ataque × zagueiros deles
    if heights is not None and not heights.empty and not P.empty and our_names:
        from src.data_lake.ids import player_core

        # rodada 12: altura confiável — 1º a lista do clube na FotMob (o próprio clube informa); Transfermarkt só quando
        # o nome é ÚNICO lá (o homônimo dava 1,95 m ao Gabriel Barbosa, que tem 1,78 m)
        hh = heights.assign(_c=heights["nome"].map(player_core), _h=pd.to_numeric(heights["altura_cm"], errors="coerce"))
        uniq = hh.groupby("_c")["_h"].nunique()
        hh = hh[hh["_c"].isin(uniq[uniq == 1].index)].dropna(subset=["_h"])
        hmap = dict(zip(hh["_c"], hh["_h"]))
        hsrc = {k: "Transfermarkt (nome único)" for k in hmap}
        try:
            with db.connect() as conn:
                fr = pd.read_sql_query("SELECT name, height FROM fotmob_rosters WHERE height IS NOT NULL", conn)
            for nm, h in zip(fr["name"], pd.to_numeric(fr["height"], errors="coerce")):
                if h == h and h:
                    hmap[player_core(nm)] = float(h)
                    hsrc[player_core(nm)] = "lista do clube (FotMob)"
        except Exception:
            pass
        cbs = regular(P)
        cbs = cbs[cbs["papel"] == "CB"] if not cbs.empty else cbs
        ours = _player_season(db, _recent_ids(db, our_names, n), our_names)
        ours = regular(ours)
        att = ours[ours["papel"].isin(["ST", "LW", "RW", "AM"])] if not ours.empty else ours
        # só conta atacante que GANHA no alto: ≥ 50% dos duelos aéreos com ≥ 6 disputas (altura sem subir não ajuda)
        def aerial(r):
            w, t = r.get("aerials_won_tot"), r.get("aerials_won_total_tot")
            try:
                w, t = float(w), float(t)
                return (w / t, int(t)) if t > 0 else (None, 0)
            except (TypeError, ValueError):
                return (None, 0)
        att_h = []
        for r in att.to_dict("records"):
            h = hmap.get(player_core(r["jogador"]))
            rate, n_ = aerial(r)
            if h and h == h and rate is not None and n_ >= 6 and rate >= .5:
                att_h.append((r["jogador"], h, rate, n_))
        for r in cbs.to_dict("records"):
            h = hmap.get(player_core(r["jogador"]))
            if not h or h != h:
                continue
            tall = [t for t in att_h if t[1] - h >= 5]
            cb_rate, cb_n = aerial(r)
            if h <= 183 and tall:
                a, ah, ar, an = max(tall, key=lambda t: (t[1] - h) * t[2])
                cb_txt = (f"; ele ganha {100 * cb_rate:.0f}% dos duelos aéreos ({cb_n})" if cb_rate is not None and cb_n >= 6 else "")
                grav = 40 + (ah - h) * 2 + (100 * ar - 50) * .5 + ((50 - 100 * cb_rate) * .5 if cb_rate is not None else 0)
                add(f"Zagueiro baixo: {r['jogador']} ({h:.0f} cm)", "defesa", None, r["jogador"],
                    f"{r['jogador']} tem {h:.0f} cm{cb_txt}; nosso {a} tem {ah:.0f} cm e ganha {100 * ar:.0f}% "
                    f"dos duelos aéreos ({an})", grav,
                    f"Bolas aéreas e cruzamentos direcionados para {a} disputar com {r['jogador']}; escanteio no setor dele.",
                    f"altura: {hsrc.get(player_core(a), 'cadastro')}; duelos aéreos dos últimos jogos (FotMob)")
    out.sort(key=lambda d: -d["gravidade"])
    # rodada 12: função de cada jogador citado + o XI habitual (para desenhar os jogadores no campinho)
    xi = []
    if not P.empty and "papel" in P:
        roles = dict(zip(P["jogador"], P["papel"]))
        for f in out:
            if f.get("jogador"):
                f["papel"] = roles.get(f["jogador"])
        reg = P.sort_values("minutos", ascending=False) if "minutos" in P else P
        gk = reg[reg["papel"] == "GK"].head(1)
        outfield = reg[reg["papel"].notna() & (reg["papel"] != "GK")].head(10)
        xi = [{"jogador": r["jogador"], "papel": r["papel"]} for r in pd.concat([gk, outfield]).to_dict("records")]
    return {"achados": out, "jogos": len(ids), "jogadores_avaliados": int(len(P)) if not P.empty else 0, "xi": xi}
