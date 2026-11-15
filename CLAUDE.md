# CLAUDE.md — Tactical Intelligence Lab (Tactical Vision)

Leia este arquivo inteiro antes de qualquer ação. Ele substitui o histórico das conversas anteriores.

## 1. O projeto

Plataforma pessoal de análise de futebol em Python + Streamlit: assistente tático que responde perguntas com
números conferidos, busca de jogos/times/jogadores, comparação, página de partida (lances, xT, redes de passe,
mapas), pontos fortes e fracos, escalação com plano de jogo, rede neural de "perigo da posse" e um lake de dados
de várias fontes abertas. Usuário: Matheus (Vanessa às vezes faz os pedidos por ele). Fale sempre em **português**,
com linguagem de futebol (não de estatístico).

**Premissa inegociável — honestidade técnica:** nunca inventar dado. Lacuna aparece como lacuna. Valor
desconhecido não vira zero. Toda estimativa diz que é estimativa e como foi feita.

## 2. Ambiente

- Windows 11 Pro · i7-4770 · GTX 1070 8 GB · 16 GB RAM.
- Pasta: `C:\Users\MATHEUS\TACTICAL_INTELLIGENCE_LAB`, venv em `.\venv` (`.\venv\Scripts\Activate.ps1`).
- Python 3.15 · Streamlit 1.67 · pyarrow instalado · `python -m pytest -q` (≈193 testes verdes na v35).
- App: `streamlit run app.py`.
- **Proibido usar `pyyaml` e `bs4`.** Use só: biblioteca padrão, httpx, pandas, numpy, duckdb, pyarrow, pytest
  (e o que já está em `requirements.txt`: scipy, plotly, mplsoccer etc.). Não adicione dependência sem necessidade.
- Visual padrão Football Manager: fundo `#090D16`, cards com borda `#1E2A44`, azul `#22D3EE`/`#3B82F6` para o time em
  foco/mandante, vermelho `#EF4444` para o adversário (`src/ui/theme.py`).

## 3. Regras de segurança (literais do usuário — valem sempre)

- NUNCA imprima, exiba em logs, registre em saídas de texto, inclua em código-fonte, testes, relatórios de execução
  ou mensagens de commit nenhuma chave ou credencial.
- **NUNCA abra, exiba ou altere o arquivo `.env`.** Para saber se uma variável existe, use código que só diga
  "definida/não definida".
- NUNCA adicione o `.env`, arquivos de banco (`*.db`), a pasta `data/` ou `data/lake` em commits.
- ANTES de cada commit, confirme que voltam vazios:
  1. `git ls-files .env`
  2. `git grep --cached -n "AI[z]a"`  (procura o prefixo das chaves Google; no código, escreva-o partido: `"AI" "za"`)
  3. `git ls-files data/lake`
  4. `git ls-files "*.db"`
- NUNCA faça `git push` sem o usuário pedir. Commits locais são ok.
- Se o GitHub bloquear um push por segredo, não libere — avise.
- NUNCA avance com testes falhando.
- Chaves do Gemini e da API-Football já foram expostas num chat antigo; o usuário foi orientado a trocá-las.

## 4. Como trabalhar neste PC (importante)

- **Não rode `python -m src.data_hub.sync` com o app aberto** — o SQLite aceita um gravador por vez e o PC fica lento.
- Antes de pedir para baixar algo, **verifique se já existe** (ver seção 6). Downloads pesados só com motivo claro.
- O usuário sempre roda todos os comandos que você manda. Prefira poucos comandos, explicados em uma linha cada.
- Ao terminar uma etapa: rode `pytest`, faça as 4 conferências, commit local, e diga em linguagem simples o que mudou.

## 5. Mapa do código

- `app.py` — navegação escondida; páginas principais (Assistente, Buscar, Comparar, Escalação) e telas de foco
  (jogo/time/jogador/competição) com pilha "← Voltar" (`src/ui/nav.py`). Barra do topo: uma busca, seletor de
  **nível de dado** (🟢 lances · 📊 estatísticas · 📄 só placar) e "só partidas reais".
- `src/ui/context.py` — cache (`cached_catalog`, `_bundle_parts` → `load_bundle`; o cache guarda só dict/DataFrame,
  nunca objetos), `chosen_levels()`.
- `src/data_hub/db.py` — SQLite (WAL, migrações por `user_version`). `stable_version()`: a interface só adota uma
  versão nova do catálogo 10 min depois da anterior (evita reler 300 mil partidas a cada clique durante um sync);
  gravações feitas pela própria tela invalidam na hora (`_touched`).
- `src/data_hub/service.py` — `MatchDataService.load()`: monta a partida (eventos/estatísticas), junta irmãos de
  outras fontes (`stats_sibling`), redireciona para a versão com lances.
- `src/data_hub/sources/*` — conectores; `src/data_hub/sync.py` (CLI `--only`, `--tudo`, `--desde`, `--ligas`),
  `autosync.py` (QUICK/DAILY, thread `til-autosync`, `AUTO_SYNC` no `.env`).
- `src/data_hub/net.py` — rede: httpx, timeout 15 s, backoff, `ascii_headers` (cabeçalho com acento quebrava tudo).
- `src/data_hub/coverage.py` → `docs/COBERTURA.md` (tamanho real da base, por fonte/competição/temporada).
- `src/data_lake/` — lake em parquet (`data/lake`), espelho opcional no SQLite, DuckDB, camada unificada de ids.
- `src/intelligence/` — `query_understanding.py` (intenção da pergunta), `scoped_evidence.py` (blocos de evidência),
  `dynamic_analyst.py` (redator local + Gemini com disjuntor), `src/guard/present.py` (confere cada número; tags
  [EXATO]/[DERIVADO] nunca aparecem na tela).
- `src/metrics/` — fatos da partida, xT, pontos fortes/fracos (percentil só no detalhe técnico).
- `src/machine_learning/` — `neural_net.py` (MLP NumPy, Adam, parada antecipada, ajuste fino),
  `model_registry.py` (GroupKFold por partida, teste isolado, bootstrap pareado por partida; CLI
  `python -m src.machine_learning.model_registry --treinar`).
- `src/squad/` — Escalação: `formations.py`, `planner.py` (nota do laboratório, melhor XI por algoritmo húngaro,
  provável XI, perfil dos últimos N jogos, plano neutralizar/explorar), `data.py` (leitura filtrada do lake).
- `src/ui/pages/` — `assistant.py`, `search_all.py`, `games.py` (foco do jogo), `match_center.py`, `clubs.py`,
  `players_search.py` (scout por 90 + carreira), `squad.py`, `compare.py`, `neural.py`, `catalog.py`.

**Convenções:** níveis `EVENTS` / `BOXSCORE` / `RESULT` / `SIMULATED` / `UPLOAD`. Ids internos por faixa de fonte:
statsbomb <10M · wyscout 10M · api_football 100M · football_data 300M · espn 500M · fdcouk 2B · openfootball 3B ·
intl 4B · understat 6B · brasileirao 7B · open_matchday 8B · cbf 9B · openplay 11B. Mesma partida em fontes
diferentes = mesma data ±1 dia + mesmos times (`_same`, `consolidate.py`); divergências são registradas, nunca
viram média. Coordenadas no padrão StatsBomb 120×80, ataque para a direita.

## 6. O que JÁ está baixado no PC do usuário (não peça de novo)

- **StatsBomb Open Data** inteiro em `C:\dados\statsbomb` (`STATSBOMB_OPEN_DATA_PATH` no `.env`).
- **OpenPlay** release `data-v0.1.0` (139 arquivos, 0,94 GB) — 26.547 jogos com lances (eventos convertidos ao abrir).
- **CBF / BrazilianFootball**: `C:\dados\cbf\results\processed\*_games.json` (65 arquivos).
- **Transfermarkt (dcaribou)**: competições, clubes, 50 mil jogadores, 656 mil valores, 89 mil jogos — e na v35
  passa a baixar `appearances` e `game_lineups`.
- **football-data.co.uk** (1993–hoje, 22 divisões + BRA/ARG/USA/MEX/JPN/CHN/AUT/DNK/FIN/IRL/NOR/POL/ROU/RUS/SWE/SWZ),
  **openfootball** (cópia git local), **seleções (intl)**, **Brasileirão Dataset (adaoduque)**, **open-matchday**,
  **Simonetti** (wc_data_*), **Wyscout** (5 ligas 17/18 + Copas).
- Base em 15/11/2026: ~300 mil partidas · ~32 mil com lances · ~64 mil com estatísticas · resto só placar.
- Backup: `python -m src.tools.backup_local` → `backups\` (não versionado).

**Fontes com limitação conhecida:**
- API-Football (plano grátis): só temporadas 2022–2024, sem `?ids=` (1 jogo por requisição), 100 req/dia; o app
  guarda isso em `source_state` e não gasta cota redescobrindo.
- ESPN histórico: dá HTTP 400 para `bra.1` em períodos antigos. Na v36 o 400 não é mais repetido com espera (era o
  "travado 10 min"): a recusa fica lembrada 7 dias, cada mês mostra progresso e, depois de 6 meses recusados, pula
  para o ano seguinte. Conferir no PC quais anos a ESPN realmente entrega.
- Understat: deu 0 partidas; a v35 não guarda mais resposta vazia em cache e mostra o motivo — conferir.
- Nenhuma fonte aberta tem lances com coordenadas do Brasileirão nem dados físicos (velocidade, distância, mapa de
  calor de tracking).

## 7. Pedidos do usuário (v36) — estado

Feito na sessão de 15/11/2026 (branch `claude/gifted-knuth-q93cbz`, testes: 216 verdes):
1. ✅ Assistente: perguntas com alvo têm resposta própria — ranking de xG/perigo (xT + xG, rede neural como 2ª
   opinião), "fulano jogou?" (`presence`), erros do jogador separados por tipo (`errors`), maior falha tática e
   ponto forte da equipe (`weakness`/`strength`). Perguntas de fato não esperam o Gemini (mais rápido). Perguntas
   que caem no panorama vão para `data/assistente_sem_alvo.jsonl` e aparecem em Bastidores (viram casos de teste).
2. ✅ Rede neural: experimentos A–D (`EXPERIMENTS` em `model_registry.py`, B primeiro), Adam, 100 épocas, lote 256,
   paciência 10, He, treino do zero; parada antecipada também dentro das dobras; L2 corrigido (era dividido pelo
   lote); várias tentativas por clique; conferência de classes (13% positivas) e das 14 variáveis; texto do critério
   atualizado. CLI: `python -m src.machine_learning.model_registry --treinar --experimentos B`.
   Achado: 9 das 14 variáveis são zonas (one-hot) quase redundantes com distância/ângulo — o teto de AUC ~0,60
   vem mais das variáveis do que da arquitetura.
3. ✅ Nota 0–10 por atuação (`src/metrics/player_rating.py`): pesos por setor, erros pesam metade, desconto do
   "esperado" por 90 min (calibração PROVISÓRIA em 3 jogos da Copa 2022), < 10 min sem nota. Aba Jogadores com
   Ataque/Passe/Defesa/Duelos e erros; nota média na página do jogador (só jogos com lances dele).
4. ✅ Rede de passes: só o XI por padrão (ou titulares e quem entrou separados); textos em linguagem de futebol.
   Corrigido o minuto de quem entra quando o nome da troca é o completo ("Randal Kolo Muani").
5. ✅ (parcial) Clicar no jogador nas tabelas da partida e do elenco abre a página; respostas do Assistente têm botões
   dos jogadores/times citados. Falta: nomes dentro de textos/cartões HTML (o Streamlit recarrega a sessão em links).
6. ✅ Comparar: qualquer jogador com lances na base, recorte último jogo / últimos 5 / temporada.
7. ✅ Lista de jogos do clube respeita o nível de dado do topo.
8. ✅ Atleta unificado na busca (`unify_people` em `src/data_lake/ids.py`): nome curto/completo/abreviado + nascimento;
   homônimos e casos ambíguos ficam separados. Clube atual pelo Transfermarkt.
9. ✅ Escalação: elenco atual pelos jogos (`apply_transfers`: saiu = jogou por outro clube depois; chegou = jogou pelo
   clube nos últimos 150 dias); campinho de arrastar (`src/ui/drag_pitch.py`, troca com o banco e de formação;
   posições ficam no navegador, não voltam ao Python); marcas E/N/F/C no campo; expectativa só com jogos recentes
   (≤ 400 dias) com lances ou ≥ 5 estatísticas.

Pendente (próximas sessões):
10. ❌ Tradução da interface (inglês/espanhol, padrão português).
11. ❌ Cobertura v36 (Brasil profundo, América do Sul, Europa, outros) + painel de fontes com saúde/cota. A sessão na
    nuvem não alcança sites externos (ESPN etc. bloqueados), então fontes novas precisam ser validadas no PC.
- Conferir no PC: ESPN histórico com a correção; Understat; rodar os experimentos B, A, C, D.
- Recalibrar `EXPECTED_PER90` da nota com mais partidas (hoje 3 jogos).

## 8. Ao final de cada sessão

Diga em poucas linhas o que mudou, quais comandos o usuário deve rodar (só os necessários) e o que ficou pendente.
Atualize a seção 6 e a seção 7 deste arquivo quando algo for baixado ou concluído.
