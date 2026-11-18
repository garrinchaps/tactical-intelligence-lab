import { useState } from "react";
import { askLab, fetchReport, runGenetic, type GeneticResult, type LabAnswer, type LabReport, type Match } from "./api";

/** Markdown mínimo da IA (negrito, títulos e listas) sem bibliotecas e sem HTML vindo da API. */
function Md({ text }: { text: string }) {
  const bold = (s: string, k: string) =>
    s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") ? <strong key={`${k}-${i}`}>{part.slice(2, -2)}</strong> : <span key={`${k}-${i}`}>{part}</span>);
  return (
    <div className="md">
      {text.split("\n").filter((l) => l.trim()).map((l, i) =>
        l.startsWith("- ") ? <p className="md-li" key={i}>• {bold(l.slice(2), String(i))}</p>
          : l.startsWith("#") ? <h4 key={i}>{l.replace(/^#+\s*/, "")}</h4>
          : <p key={i}>{bold(l, String(i))}</p>)}
    </div>
  );
}

const EXAMPLES = ["Como explorar o adversário?", "Quem mais criou chances?", "Como o rival reagiu às inversões de jogo?"];

export function LabAssistant({ matches }: { matches: Match[] }) {
  const analyzable = matches.filter((m) => m.data_level === "EVENTS" || m.data_level === "BOXSCORE");
  const [matchId, setMatchId] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<LabAnswer | null>(null);
  const [report, setReport] = useState<LabReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = matchId ?? analyzable[0]?.match_id ?? null;

  async function ask(q: string) {
    if (!current || !q.trim()) return;
    setBusy(true); setError(""); setQuestion(q);
    try { setAnswer(await askLab(current, q)); } catch (e) { setError(e instanceof Error ? e.message : "Erro"); }
    finally { setBusy(false); }
  }
  async function loadReport() {
    if (!current) return;
    setBusy(true); setError("");
    try { setReport(await fetchReport(current)); } catch (e) { setError(e instanceof Error ? e.message : "Erro"); }
    finally { setBusy(false); }
  }

  return (
    <section className="panel lab-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">IA DO LABORATÓRIO</span><h3>Pergunte sobre o jogo</h3></div>
        <span className="count">nossa IA · aprende com avaliações</span>
      </div>
      {analyzable.length === 0 ? <p className="muted">Escolha "Com estatísticas" ou "Com eventos" no filtro acima.</p> : (
        <>
          <div className="lab-row">
            <select value={current ?? ""} onChange={(e) => { setMatchId(Number(e.target.value)); setAnswer(null); setReport(null); }}>
              {analyzable.map((m) => <option key={m.match_id} value={m.match_id}>{m.match_date} · {m.home_team_name} {m.home_score ?? "–"}×{m.away_score ?? "–"} {m.away_team_name}</option>)}
            </select>
            <button className="ghost" onClick={loadReport} disabled={busy}>📑 Relatório completo</button>
          </div>
          <form className="lab-row" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ex.: como explorar o adversário?" />
            <button type="submit" disabled={busy}>{busy ? "Analisando…" : "Perguntar"}</button>
          </form>
          <div className="chips">{EXAMPLES.map((q) => <button key={q} className="chip" onClick={() => void ask(q)}>{q}</button>)}</div>
          {error && <p className="error">{error}</p>}
          {answer && <article className="lab-answer"><small>{answer.engine} · {answer.n_facts} fatos lidos</small><Md text={answer.markdown} /></article>}
          {report && (
            <article className="lab-answer">
              <small>Relatório · {report.nivel} · {report.n_fatos} fatos · seletor v{String(report.versao).padStart(3, "0")}</small>
              <h4>🎯 Plano para {report.foco} x {report.rival}</h4>
              {report.plano.map((p, i) => <p className="md-li" key={i}>• {p}</p>)}
              <div className="report-grid">{report.secoes.map((s) => (
                <div key={s.titulo}><h4>{s.titulo}</h4>{s.linhas.map((l, i) => <Md key={i} text={l} />)}{s.leitura && <small>Leitura: {s.leitura}</small>}</div>
              ))}</div>
              {Object.entries(report.inversoes).map(([team, e]) => (
                <p key={team}>🔁 <strong>{team}</strong>: {e.total} inversões sofridas, {e.sem_reacao} sem ninguém na bola em 5 s{e.lado_mais_fragil ? `; lado mais frágil: ${e.lado_mais_fragil}` : ""}.</p>
              ))}
              <small>{report.limites.join(" ")}</small>
            </article>
          )}
        </>
      )}
    </section>
  );
}

const SAMPLE = [
  ["Goleiro A", "GK", 70], ["Goleiro B", "GK", 58], ["Zagueiro A", "CB", 72], ["Zagueiro B", "CB", 68], ["Zagueiro C", "CB", 60],
  ["Lateral E", "LB", 66], ["Lateral D", "RB", 65], ["Volante", "DM", 70], ["Meia A", "CM", 71], ["Meia B", "CM", 64],
  ["Meia-atacante", "AM", 69], ["Ponta E", "LW", 73], ["Ponta D (driblador)", "RW", 66], ["Ponta D", "RW", 70],
  ["Centroavante (alto)", "ST", 68], ["Centroavante", "ST", 72],
].map(([nome, papel, nota]) => ({ nome, papel, nota, drible: nome === "Ponta D (driblador)" ? 0.95 : 0.4, aereo: String(nome).includes("alto") ? 0.95 : 0.4 }));

export function GeneticPanel() {
  const [res, setRes] = useState<GeneticResult | null>(null);
  const [error, setError] = useState("");
  async function run() {
    setError("");
    try {
      setRes(await runGenetic({ players: SAMPLE, formation: "4-3-3", findings: [
        { titulo: "Lateral-esquerdo rival é muito driblado", lado: "esquerda", gravidade: 95 },
        { titulo: "Zagueiro baixo: rival (176 cm)", lado: null, gravidade: 85 }] }));
    } catch (e) { setError(e instanceof Error ? e.message : "Erro"); }
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <div><span className="eyebrow">COMPUTAÇÃO EVOLUCIONÁRIA</span><h3>Escalação por algoritmo genético</h3></div>
        <span className="count">elenco de EXEMPLO · no app usa o elenco real</span>
      </div>
      <p className="muted">Aptidão = Σ nota × encaixe + bônus por explorar cada fraqueza do rival. Comparado com o melhor XI do algoritmo húngaro.</p>
      <button onClick={() => void run()}>🧬 Rodar 150 gerações</button>
      {error && <p className="error">{error}</p>}
      {res && (
        <div className="lab-answer">
          <p><strong>Aptidão:</strong> {res.aptidao} (melhor XI húngaro: {res.aptidao_base}, ganho {res.ganho >= 0 ? "+" : ""}{res.ganho})</p>
          {res.mudancas.map(([papel, de, para], i) => <p className="md-li" key={i}>• {papel}: sai {de}, entra <strong>{para}</strong></p>)}
          <div className="ga-grid">{res.xi.map((s) => (
            <div key={s.vaga} className="ga-slot"><small>{s.papel_pt}</small><strong>{s.jogador}</strong><small>encaixe {s.encaixe} · bônus {s.bonus}</small></div>
          ))}</div>
        </div>
      )}
    </section>
  );
}
