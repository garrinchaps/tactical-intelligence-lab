# Dados de demonstração (offline)

- `statsbomb_events_*.json.gz`: eventos de 3 partidas da Copa do Mundo 2022 (final e semifinais), do
  **StatsBomb Open Data** — uso com crédito à StatsBomb. Permitem abrir o app sem internet.
- `statsbomb_demo_matches.json`: metadados dessas partidas (entram no catálogo automaticamente).
- `danger_sample_wc2022.csv.gz`: amostra (250 ações por partida, 64 partidas) do dataset de perigo de posse
  gerado por `src/machine_learning/danger_dataset.py` a partir do StatsBomb Open Data + StatsBomb 360.
  Usada para treinar a rede neural ao vivo na página "Rede Neural do Zero".
