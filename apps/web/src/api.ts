export type Match = {
  match_id: number;
  competition_name: string;
  season_name: string;
  match_date: string | null;
  home_team_name: string;
  away_team_name: string;
  home_score: number | null;
  away_score: number | null;
  data_level: string | null;
  data_source: string | null;
};

export type ModelCard = {
  id: string;
  name: string;
  pillar: string;
  task: string;
  status: string;
  implementation: string;
  inputs: string[];
  outputs: string[];
  metrics: string[];
  limitations: string[];
  version: string;
};

export type FuzzyPlayerResult = {
  model: string;
  score: number;
  is_probability: boolean;
  activated_rules: Array<{ rule: string; strength: number; then: string }>;
  explanation: string;
};

export type FuzzyPressureResult = {
  model: string;
  pressure_index: number;
  is_probability: boolean;
  rule_weights: Record<string, number>;
  explanation: string;
};

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export async function fetchMatches(level?: string): Promise<Match[]> {
  const params = new URLSearchParams({ limit: "30" });
  if (level) params.set("data_level", level);
  const response = await fetch(`${API_URL}/api/v1/matches?${params}`);
  if (!response.ok) throw new Error("Não foi possível carregar as partidas.");
  const data = (await response.json()) as { items: Match[] };
  return data.items;
}

export async function fetchModels(): Promise<ModelCard[]> {
  const response = await fetch(`${API_URL}/api/v1/models`);
  if (!response.ok) throw new Error("Não foi possível carregar o catálogo de modelos.");
  const data = (await response.json()) as { items: ModelCard[] };
  return data.items;
}

export async function evaluateFuzzyPlayer(defensiveIntensity: number, passAccuracy: number): Promise<FuzzyPlayerResult> {
  const response = await fetch(`${API_URL}/api/v1/ai/fuzzy/player`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ defensive_intensity: defensiveIntensity, pass_accuracy: passAccuracy }),
  });
  if (!response.ok) throw new Error("Não foi possível avaliar o rating fuzzy.");
  return (await response.json()) as FuzzyPlayerResult;
}

export async function evaluateFuzzyPressure(
  possessionPct: number,
  territorialEntries: number,
  shots: number,
  minute: number,
): Promise<FuzzyPressureResult> {
  const response = await fetch(`${API_URL}/api/v1/ai/fuzzy/pressure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      possession_pct: possessionPct,
      territorial_entries: territorialEntries,
      shots,
      minute,
    }),
  });
  if (!response.ok) throw new Error("Não foi possível calcular a pressão fuzzy.");
  return (await response.json()) as FuzzyPressureResult;
}

export type LabAnswer = {
  markdown: string;
  engine: string;
  n_facts: number;
  facts: Array<{ key: string; team: string; player: string | null; score: number }>;
};

export type LabReport = {
  foco: string;
  rival: string;
  nivel: string;
  n_fatos: number;
  versao: number;
  plano: string[];
  secoes: Array<{ titulo: string; linhas: string[]; leitura: string }>;
  jogadores: Record<string, string[]>;
  inversoes: Record<string, { total: number; sem_reacao: number; lado_mais_fragil?: string | null; tabela: Array<Record<string, string | number>> }>;
  limites: string[];
};

export type GeneticSlot = { vaga: number; papel_pt: string; jogador: string; encaixe: number; bonus: number; porque: string[] };
export type GeneticResult = {
  aptidao: number; aptidao_base: number; ganho: number; formacao: string;
  xi: GeneticSlot[]; mudancas: Array<[string, string, string]>; historico: number[];
};

export async function askLab(matchId: number, question: string): Promise<LabAnswer> {
  const response = await fetch(`${API_URL}/api/v1/ai/lab/ask`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ match_id: matchId, question }),
  });
  if (!response.ok) throw new Error("A IA do laboratório não conseguiu responder.");
  return (await response.json()) as LabAnswer;
}

export async function fetchReport(matchId: number): Promise<LabReport> {
  const response = await fetch(`${API_URL}/api/v1/matches/${matchId}/report`);
  if (!response.ok) throw new Error("Não foi possível montar o relatório.");
  return (await response.json()) as LabReport;
}

export async function runGenetic(body: unknown): Promise<GeneticResult> {
  const response = await fetch(`${API_URL}/api/v1/ai/genetic/lineup`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("O algoritmo genético não rodou.");
  return (await response.json()) as GeneticResult;
}
