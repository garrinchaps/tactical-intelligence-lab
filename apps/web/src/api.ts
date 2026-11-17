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
