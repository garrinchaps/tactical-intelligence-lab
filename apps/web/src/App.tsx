import { useEffect, useState } from "react";
import {
  evaluateFuzzyPlayer,
  evaluateFuzzyPressure,
  fetchMatches,
  fetchModels,
  type FuzzyPlayerResult,
  type FuzzyPressureResult,
  type Match,
  type ModelCard,
} from "./api";
import { GeneticPanel, LabAssistant } from "./LabPanels";

const levels = [
  { value: "", label: "Todas as partidas" },
  { value: "EVENTS", label: "Com eventos" },
  { value: "BOXSCORE", label: "Com estatísticas" },
  { value: "RESULT", label: "Apenas placar" },
];

export function App() {
  const [level, setLevel] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [models, setModels] = useState<ModelCard[]>([]);
  const [playerRating, setPlayerRating] = useState<FuzzyPlayerResult | null>(null);
  const [pressure, setPressure] = useState<FuzzyPressureResult | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchMatches(level)
      .then((items) => active && setMatches(items))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Erro inesperado."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [level]);

  useEffect(() => {
    fetchModels().then(setModels).catch(() => setModels([]));
  }, []);

  useEffect(() => {
    Promise.all([
      evaluateFuzzyPlayer(75, 85),
      evaluateFuzzyPressure(65, 70, 50, 45),
    ]).then(([player, matchPressure]) => {
      setPlayerRating(player);
      setPressure(matchPressure);
    }).catch(() => {
      setPlayerRating(null);
      setPressure(null);
    });
  }, []);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">INTELLIGENCE PLATFORM</span>
          <h1>Tactical Intelligence Lab</h1>
        </div>
        <span className="status"><i /> Data Hub online</span>
      </header>
      <section className="hero">
        <div>
          <span className="eyebrow">MATCH CENTER</span>
          <h2>Leia o jogo com contexto.</h2>
          <p>Resultados, eventos e estatísticas em uma camada de inteligência preparada para scouting.</p>
        </div>
        <div className="hero-mark">TIL<span>01</span></div>
      </section>
      <section className="toolbar" aria-label="Filtros de partidas">
        <label htmlFor="level">Profundidade dos dados</label>
        <select id="level" value={level} onChange={(event) => setLevel(event.target.value)}>
          {levels.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </section>
      <LabAssistant matches={matches} />
      <GeneticPanel />
      <section className="panel">
        <div className="panel-heading"><div><span className="eyebrow">RECENTES</span><h3>Partidas disponíveis</h3></div><span className="count">{matches.length} carregadas</span></div>
        {loading && <p className="muted">Carregando catálogo…</p>}
        {error && <p className="error">{error} Verifique se a API está disponível.</p>}
        {!loading && !error && <div className="match-list">{matches.map((match) => (
          <article className="match" key={match.match_id}>
            <div><span className="competition">{match.competition_name} · {match.season_name}</span><strong>{match.home_team_name}</strong><strong>{match.away_team_name}</strong></div>
            <div className="score"><b>{match.home_score ?? "–"} : {match.away_score ?? "–"}</b><span>{match.data_level ?? "SEM NÍVEL"}</span></div>
          </article>
        ))}</div>}
      </section>
      <section className="panel model-panel">
        <div className="panel-heading"><div><span className="eyebrow">AI LAB</span><h3>Modelos e limitações</h3></div><span className="count">{models.length} catalogados</span></div>
        <div className="model-grid">{models.map((model) => (
          <article className="model-card" key={model.id}>
            <span className="eyebrow">{model.pillar}</span>
            <h4>{model.name}</h4>
            <p>{model.task} · {model.status}</p>
            <small>Métricas: {model.metrics.join(", ")}</small>
            <small>Limitação: {model.limitations[0]}</small>
          </article>
        ))}</div>
      </section>
      <section className="panel fuzzy-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">EXPLICABILIDADE</span><h3>Indicadores fuzzy</h3></div>
          <span className="count">Mamdani · Sugeno</span>
        </div>
        <div className="fuzzy-grid">
          <article className="fuzzy-card">
            <span className="eyebrow">RATING DE JOGADOR</span>
            <strong>{playerRating ? `${playerRating.score.toFixed(1)} / 100` : "–"}</strong>
            <p>{playerRating?.explanation ?? "Aguardando API…"}</p>
            <small>{playerRating?.activated_rules.length ?? 0} regras ativadas</small>
          </article>
          <article className="fuzzy-card">
            <span className="eyebrow">PRESSÃO TERRITORIAL</span>
            <strong>{pressure ? `${pressure.pressure_index.toFixed(1)} / 100` : "–"}</strong>
            <p>{pressure?.explanation ?? "Aguardando API…"}</p>
            <small>{pressure ? `${Object.keys(pressure.rule_weights).length} pesos de regras` : ""}</small>
          </article>
        </div>
      </section>
      <footer>Dados servidos pelo Tactical Intelligence Data Hub · fontes e licenças preservadas por manifesto.</footer>
    </main>
  );
}
