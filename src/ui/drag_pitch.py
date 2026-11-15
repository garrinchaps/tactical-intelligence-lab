"""
Campinho interativo de arrastar (estilo Football Manager), sem dependência nova: HTML + JS dentro do Streamlit.

* arraste qualquer jogador para outro ponto do campo;
* arraste um reserva do banco para cima de um titular para trocar os dois;
* troque a formação no seletor (as posições mudam na hora, os jogadores ficam);
* "Copiar escalação" copia o XI em texto. As posições ficam guardadas no próprio navegador (por time).

Limite honesto: o que você arrasta aqui não volta para o Python (o Streamlit não recebe esse retorno sem um
componente próprio). A nota média e o plano de jogo continuam calculados sobre a escalação montada acima.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from src.squad.formations import FORMATIONS, ROLE_PT


def _color(p: Dict[str, Any]) -> str:
    e = p.get("encaixe") or 0
    return "#22D3EE" if e >= 0.85 else ("#F59E0B" if e >= 0.6 else "#EF4444")


def html(team: str, formation: str, xi: List[Dict[str, Any]], bench: List[Dict[str, Any]],
         tips: List[Dict[str, Any]] | None = None, height: int = 640) -> str:
    players = [{"id": f"p{i}", "nome": p.get("jogador") or "vaga", "nota": p.get("nota"), "papel": p.get("papel_pt", ""),
                "cor": _color(p)} for i, p in enumerate(xi)]
    reserves = [{"id": f"b{i}", "nome": b.get("nome") or "", "nota": b.get("nota"), "papel": b.get("papel_pt", ""),
                 "cor": "#64748B"} for i, b in enumerate(bench[:14])]
    forms = {k: [[x, y, ROLE_PT.get(r, r)] for r, x, y in v] for k, v in FORMATIONS.items()}
    data = json.dumps({"team": team, "formation": formation, "players": players, "bench": reserves, "forms": forms,
                       "tips": tips or []}, ensure_ascii=False)
    return """
<div id="fm" style="font-family:Inter,system-ui,sans-serif;color:#E2E8F0;background:#090D16;border:1px solid #1E2A44;
     border-radius:12px;padding:10px">
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
    <b id="fm_t"></b>
    <select id="fm_f" style="background:#0F172A;color:#E2E8F0;border:1px solid #1E2A44;border-radius:6px;padding:4px"></select>
    <button id="fm_r" style="background:#0F172A;color:#E2E8F0;border:1px solid #1E2A44;border-radius:6px;padding:4px 8px">↺ Posições da formação</button>
    <button id="fm_c" style="background:#0F172A;color:#22D3EE;border:1px solid #1E2A44;border-radius:6px;padding:4px 8px">📋 Copiar escalação</button>
    <span id="fm_msg" style="color:#94A3B8;font-size:12px"></span>
  </div>
  <svg id="fm_s" viewBox="-2 -2 124 84" style="width:100%;max-height:%%H%%px;touch-action:none;background:#0B3D2E;border-radius:8px">
    <g stroke="rgba(255,255,255,.55)" stroke-width=".35" fill="none">
      <rect x="0" y="0" width="120" height="80"/><line x1="60" y1="0" x2="60" y2="80"/><circle cx="60" cy="40" r="10"/>
      <rect x="0" y="18" width="18" height="44"/><rect x="102" y="18" width="18" height="44"/>
      <rect x="0" y="30" width="6" height="20"/><rect x="114" y="30" width="6" height="20"/>
    </g>
    <text x="118" y="4" fill="rgba(255,255,255,.4)" font-size="2.6" text-anchor="end">ataque →</text>
    <g id="fm_tips"></g><g id="fm_p"></g>
  </svg>
  <div style="margin-top:8px;font-size:12px;color:#94A3B8">Banco — arraste um reserva para cima de um titular para trocar:</div>
  <div id="fm_b" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px"></div>
</div>
<script>
(function(){
const D = %%DATA%%;
const key = "til_fm_" + D.team;
let st = null;
try { st = JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { st = null; }
let form = (st && D.forms[st.form]) ? st.form : D.formation;
let pos = (st && st.pos && st.form === form) ? st.pos : null;
let XI = (st && st.xi && st.xi.length === D.players.length) ? st.xi : D.players.map(p => p.id);
const all = {}; D.players.concat(D.bench).forEach(p => all[p.id] = p);
let BENCH = D.bench.map(b => b.id).filter(id => XI.indexOf(id) < 0).concat(D.players.map(p => p.id).filter(id => XI.indexOf(id) < 0));
const svg = document.getElementById("fm_s"), G = document.getElementById("fm_p");
document.getElementById("fm_t").textContent = D.team;
const sel = document.getElementById("fm_f");
Object.keys(D.forms).forEach(f => { const o = document.createElement("option"); o.value = f; o.textContent = f; if (f === form) o.selected = true; sel.appendChild(o); });
function base(){ return D.forms[form].map(s => [s[0], s[1]]); }
if (!pos) pos = base();
function save(){ try { localStorage.setItem(key, JSON.stringify({form, pos, xi: XI})); } catch (e) {} }
function last(n){ const t = (n || "").split(" "); return t[t.length - 1]; }
function pt(ev){ const r = svg.getBoundingClientRect(); const vb = svg.viewBox.baseVal;
  return [vb.x + (ev.clientX - r.left) / r.width * vb.width, vb.y + (ev.clientY - r.top) / r.height * vb.height]; }
function draw(){
  G.innerHTML = "";
  XI.forEach((id, i) => {
    const p = all[id], [x, y] = pos[i], role = D.forms[form][i][2];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("transform", `translate(${x},${y})`); g.style.cursor = "grab"; g.dataset.i = i;
    g.innerHTML = `<circle r="3.6" fill="${p.cor}" stroke="#E2E8F0" stroke-width=".5"/>
      <text y="1.1" font-size="2.6" text-anchor="middle" fill="#090D16" font-weight="700">${p.nota != null ? Math.round(p.nota) : ""}</text>
      <text y="6.6" font-size="2.5" text-anchor="middle" fill="#F5F7FB">${last(p.nome)}</text>
      <text y="-4.6" font-size="1.8" text-anchor="middle" fill="rgba(255,255,255,.65)">${role}</text>
      <title>${p.nome} · ${p.papel || role}${p.nota != null ? " · nota " + p.nota : ""}</title>`;
    g.addEventListener("pointerdown", ev => { ev.preventDefault(); g.setPointerCapture(ev.pointerId); g.dataset.drag = "1"; });
    g.addEventListener("pointermove", ev => { if (g.dataset.drag !== "1") return; const [nx, ny] = pt(ev);
      pos[i] = [Math.max(1, Math.min(119, nx)), Math.max(1, Math.min(79, ny))]; g.setAttribute("transform", `translate(${pos[i][0]},${pos[i][1]})`); });
    g.addEventListener("pointerup", () => { g.dataset.drag = ""; save(); });
    G.appendChild(g);
  });
  const B = document.getElementById("fm_b"); B.innerHTML = "";
  BENCH.forEach(id => { const p = all[id]; if (!p || !p.nome) return;
    const d = document.createElement("div"); d.draggable = true; d.textContent = `${p.nome}${p.nota != null ? " · " + Math.round(p.nota) : ""}`;
    d.title = p.papel || ""; d.style.cssText = "background:#0F172A;border:1px solid #1E2A44;border-radius:14px;padding:3px 9px;font-size:12px;cursor:grab";
    d.addEventListener("dragstart", ev => ev.dataTransfer.setData("text/plain", id));
    d.addEventListener("pointerdown", () => { window._fmPick = id; document.getElementById("fm_msg").textContent = "Toque num titular para trocar por " + p.nome; });
    B.appendChild(d); });
  const T = document.getElementById("fm_tips"); T.innerHTML = "";
  (D.tips || []).forEach(t => { const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.innerHTML = `<circle cx="${t.x}" cy="${t.y}" r="2.4" fill="${t.cor}" opacity=".85"/><text x="${t.x}" y="${t.y + .9}" font-size="2.3" text-anchor="middle" fill="#090D16" font-weight="700">${t.marca}</text><title>${t.texto}</title>`;
    T.appendChild(g); });
}
function swap(benchId, i){ const out = XI[i]; XI[i] = benchId; BENCH = BENCH.filter(b => b !== benchId); BENCH.unshift(out); save(); draw();
  document.getElementById("fm_msg").textContent = `${all[benchId].nome} entrou no lugar de ${all[out].nome}`; }
svg.addEventListener("dragover", ev => ev.preventDefault());
svg.addEventListener("drop", ev => { ev.preventDefault(); const id = ev.dataTransfer.getData("text/plain"); if (!id) return;
  const [x, y] = pt(ev); let best = 0, bd = 1e9; pos.forEach((p, i) => { const d = (p[0] - x) ** 2 + (p[1] - y) ** 2; if (d < bd) { bd = d; best = i; } }); swap(id, best); });
G.addEventListener("click", ev => { const g = ev.target.closest("g[data-i]"); if (g && window._fmPick) { swap(window._fmPick, +g.dataset.i); window._fmPick = null; } });
sel.addEventListener("change", () => { form = sel.value; pos = base(); save(); draw(); });
document.getElementById("fm_r").addEventListener("click", () => { pos = base(); save(); draw(); });
document.getElementById("fm_c").addEventListener("click", () => {
  const txt = D.team + " (" + form + "): " + XI.map((id, i) => D.forms[form][i][2] + " " + all[id].nome).join(", ");
  try { navigator.clipboard.writeText(txt); document.getElementById("fm_msg").textContent = "Escalação copiada."; }
  catch (e) { document.getElementById("fm_msg").textContent = txt; } });
draw();
})();
</script>
""".replace("%%DATA%%", data).replace("%%H%%", str(height))


# onde cada indicador "mora" no campo (ataque para a direita): (x, y) no campo do rival / no nosso campo
ZONES = {
    "crosses_total": ((100, 8), (20, 72)), "corners": ((116, 4), (4, 76)), "shots_total": ((106, 40), (14, 40)),
    "shots_on_target": ((110, 46), (10, 34)), "xg": ((104, 34), (16, 46)), "big_chances": ((108, 30), (12, 50)),
    "goals": ((112, 40), (8, 40)), "possession_pct": ((62, 24), (58, 56)), "passes_total": ((68, 34), (52, 46)),
    "pass_accuracy_pct": ((74, 46), (46, 34)), "dribbles_completed": ((88, 60), (32, 20)),
    "aerials_won": ((98, 40), (22, 40)), "tackles_won": ((70, 60), (50, 20)), "interceptions": ((78, 20), (42, 60)),
    "fouls": ((84, 52), (36, 28)), "yellow_cards": ((80, 66), (40, 14)),
}


def pitch_tips(plan: Dict[str, Any] | None, rival_corr: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """
    Leitura tática espalhada pelo campo: E = explorar (fraqueza do rival), N = neutralizar (força do rival),
    F = nossa força para usar, C = cuidado (nossa fraqueza). Cada marca diz o número que a sustenta.
    """
    if not plan:
        return []
    out: List[Dict[str, Any]] = []
    used: Dict[tuple, int] = {}

    def put(key, side, mark, color, text):
        z = ZONES.get(key)
        if not z:
            return
        x, y = z[0] if side == "rival" else z[1]
        n = used.get((x, y), 0)
        used[(x, y)] = n + 1
        out.append({"x": x, "y": y + 5 * n, "marca": mark, "cor": color, "texto": text})

    for i, d in enumerate(plan.get("explorar") or [], 1):
        put(d["chave"], "rival", f"E{i}", "#22C55E", f"Explorar: {d['acao']} (rival {d['rotulo'].lower()} {d['media']}, "
                                                      f"{d['dif_pct']:+.0f}% vs. média)")
    for i, d in enumerate(plan.get("neutralizar") or [], 1):
        put(d["chave"], "nosso", f"N{i}", "#EF4444", f"Neutralizar: {d['acao']} (rival {d['rotulo'].lower()} {d['media']}, "
                                                     f"{d['dif_pct']:+.0f}%)")
    for i, d in enumerate((plan.get("nossos_fortes") or [])[:3], 1):
        put(d["chave"], "rival", f"F{i}", "#22D3EE", f"Nossa força: {d['rotulo']} {d['media']} ({d['dif_pct']:+.0f}% vs. média)")
    for i, d in enumerate((plan.get("nossos_fracos") or [])[:3], 1):
        put(d["chave"], "nosso", f"C{i}", "#F59E0B", f"Cuidado (nosso ponto fraco): {d['rotulo']} {d['media']} "
                                                     f"({d['dif_pct']:+.0f}% vs. média)")
    rc = rival_corr or {}
    if rc.get("ataca_por"):
        side, pct = max(rc["ataca_por"].items(), key=lambda kv: kv[1])
        y = {"esquerda": 70, "centro": 40, "direita": 10}[side]
        out.append({"x": 30, "y": y, "marca": "⛔", "cor": "#EF4444", "texto": f"O rival chega mais por aqui ({pct:.0f}% das chegadas)"})
    if rc.get("sofre_por"):
        side, pct = max(rc["sofre_por"].items(), key=lambda kv: kv[1])
        y = {"esquerda": 12, "centro": 40, "direita": 68}[side]
        out.append({"x": 92, "y": y, "marca": "➜", "cor": "#22C55E", "texto": f"O rival mais sofre por aqui ({pct:.0f}%)"})
    return out
