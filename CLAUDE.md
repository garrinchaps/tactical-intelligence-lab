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
  passa a baixar `appearances` e `game_lineups`. Na v36 passa a baixar também `transfers` (`tm_transferencias`,
  base do vínculo jogador-clube) — conferir se o usuário já rodou `--only transfermarkt` depois da v36.
- **football-data.co.uk** (1993–hoje, 22 divisões + BRA/ARG/USA/MEX/JPN/CHN/AUT/DNK/FIN/IRL/NOR/POL/ROU/RUS/SWE/SWZ),
  **openfootball** (cópia git local), **seleções (intl)**, **Brasileirão Dataset (adaoduque)**, **open-matchday**,
  **Simonetti** (wc_data_*), **Wyscout** (5 ligas 17/18 + Copas).
- Base em 15/11/2026: ~300 mil partidas · ~32 mil com lances · ~64 mil com estatísticas · resto só placar.
- Backup: `python -m src.tools.backup_local` → `backups\` (não versionado).

**Fontes com limitação conhecida:**
- API-Football (plano grátis): só temporadas 2022–2024, sem `?ids=` (1 jogo por requisição), 100 req/dia; o app
  guarda isso em `source_state` e não gasta cota redescobrindo.
- ESPN: **causa raiz achada em 16/11/2026** — a ESPN passou a RECUSAR qualquer intervalo de datas
  (`dates=20251001-20251007` → HTTP 400 em TODAS as ligas). Aceita só dia (`20251004`), mês (`202510`) ou ano (`2025`).
  O conector agora pede por ano/mês. Validado daqui: 52 ligas com jogos 2025/2026 (~25 mil encerrados); fora:
  `bra.supercopa`, `kor.1`; Série C 2026 vazia. Comandos: `--only espn_temporada` (resultados + próximos jogos,
  ~1 pedido por liga/ano), `--only espn_resumos --limite N` (estatísticas + escalações + números por jogador, ~1 s
  cada, Brasil e Europa principal primeiro, continua de onde parou), `--only espn_elencos` (elenco atual + lesões).
  A ESPN agora vem LIGADA por padrão (ENABLE_ESPN_PUBLIC_FEED=false desliga).
- Understat: deu 0 partidas porque o SITE ESTÁ FORA DO AR ("We will come back soon", conferido em 16/11/2026) — não é
  defeito do PC nem do conector.
- **FotMob (rodada 5, NOVA)**: JSON público do site (`/api/data/leagues`, `/api/data/matchDetails`), sem chave. ~100
  competições (`LEAGUES` em `src/data_hub/sources/fotmob.py`: Série A–D, Copa do Brasil, estaduais, Copa do Nordeste,
  sul-americanas, 1ª/2ª divisões europeias e copas, feminino, MLS, Liga MX), até 5 temporadas. Por jogo: estatísticas
  com xG/xGOT/xG de bola parada (distância/sprints só onde a liga mede, ex. Premier League), escalação com posição
  EXATA (layout), números por jogador (xA, chances criadas, passes no terço final, recuperações, duelos, nota da
  FotMob, id do atleta), mapa de chutes (`match_shots`), cartões, gols, substituições, desfalques. ~35 KB por jogo.
  Comandos: `--only fotmob_temporada --temporadas N` (resultados + calendário), `--only fotmob_jogos --limite N`
  (detalhes, retomável). Automático só com `ENABLE_FOTMOB=true` no .env (o usuário põe; nunca abrir o .env).
  Ids: faixa 12B. Uso pessoal e não comercial.
- Bloqueiam robôs (403, não contornar): FBref, Sofascore, zerozero/ogol, worldfootball. Pagas/sob contrato (não
  integradas, exigem chave/plano): Sportmonks, Sportradar, Opta/Stats Perform (Opta Vision), Wyscout (só o dataset
  aberto 17/18 que já temos), StatsBomb comercial. football-data.org precisa de chave (conector já existe).
- Nenhuma fonte aberta tem lances com coordenadas do Brasileirão nem dados físicos (velocidade, distância, mapa de
  calor de tracking).

## 7. Pedidos do usuário (v36) — estado

Feito na sessão 1 (15/11/2026, branch `claude/gifted-knuth-q93cbz`, 216 testes verdes):
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

Lista A–J do usuário (sessão 2, 16/11/2026) — 233 testes verdes:
- ✅ A1 ESPN em janelas 7 → 3 → 1 dia (400 = janela recusada, contada em `janelas_falhas`) · A2 rede de passes com
  os 11 em campo num minuto (`on_field`) · A3/A4 (presença/falha tática) · A5 filtro de nível na consulta SQL.
- ✅ B2 `sync_policy.py`: incremental por competição, ao vivo a cada 1 min (só ligas com jogo rolando; varredura a
  cada 15 min), encerrada consolidada e congelada (`frozen_matches`), fixtures a cada 3 h · B3 `src/squad/tenure.py`
  (transferências + jogos, empréstimo/retorno, UNKNOWN fora do elenco) · B4 `src/data_hub/player_resolver.py`
  (nunca só o nome; `player_merge_candidates`) · B5 `python -m src.tools.cache_crests` (data/crests) + monograma ·
  B6 `src/data_hub/depth.py` (nível 0–4, selo na página do jogo) · B7 `source_divergences`.
- ✅ C `src/analytics/player_ratings.py` (pares por setor/competição com n ≥ 20, média com n mínimo 3 e minutos,
  abas Defensivo/Ofensivo/Passes, teste zagueiro × atacante).
- ✅ D campinho com tamanho ajustável e formação customizada; marcas em linguagem de futebol; diagnóstico do rival
  (2 fortes + 2 fracos com dado e jogo de origem; só jogos nível ≥ 2, senão "base insuficiente").
- ✅ E1 latência medida (`data/assistente_latencia.jsonl`, painel em Bastidores, meta < 8 s) · E5 "não tenho esse
  dado" · E3/E4 intocados.
- ✅ F1 cartões 14px · F2 idioma PT/EN/ES (`src/ui/i18n.py`) · F3 Fortes e fracos em cartões com barra · F4
  "o que é isto?" (`src/ui/glossary.py`) · F8 comparar qualquer jogador.
- ✅ G painel de fontes (aba 🩺 em Dados & Fontes, `src/data_hub/health.py`, ações em segundo plano).

Rodada 3 (16/11/2026, 247 testes verdes; testes não acessam a rede — `tests/conftest.py`):
- ✅ ESPN por ano/mês + fixtures (`fixtures`) + elencos (`espn_rosters`) + resumos priorizados; atualização automática
  (QUICK `espn` = temporada do ano + resumos da última semana; DAILY `espn_elencos`; ao vivo pela ESPN).
- ✅ Busca de jogos ordenada por data (o nome só filtra).
- ✅ Assistente: blocos táticos novos (`src/intelligence/tactical_blocks.py` + `tactical_writers.py`): corredores,
  como sofreu, entre linhas, eficiência, momentos, jogadas dos gols, diagnóstico dos defensores, duplas, erros que
  viraram perigo, plano para explorar a defesa; jogador ausente; gentílicos; pergunta de jogador sem bloco do time;
  teto de 10 s por pergunta para o Gemini (antes até ~58 s). Guard: inteiro só deriva de dois inteiros.
- ✅ Treino da rede em processo separado (`src/machine_learning/train_job.py`), andamento ao vivo, parar; float32.
- ✅ Escalação: aba 🔭 Próximo jogo (`src/squad/matchday.py`): calendário real, provável dos dois times pelas escalações
  recentes (posição e lado), lesões (ESPN) e suspensões (vermelho no último jogo), fragilidades por setor no campinho,
  quem decide, porquê de cada jogador; Provável/Melhor usam escalações reais quando há ≥ 3 jogos; 16 formações.
- ✅ Comparar em cartões (`duel_bars`), tabelas com 2 casas, campinho sem eixos de jardas, gramado listrado.
- Observação: a ESPN lista o volante Rodri (nasc. 22/06/1996) no elenco do Barcelona hoje; o usuário disse que ele não
  é do Barcelona — fontes divergem; a interface mostra a fonte do elenco.

Rodada 4 (16/11/2026, 259 testes verdes):
- ✅ Avaliação individual 2.0 (`src/analytics/rating_v2.py`): 7 dimensões na linha com pesos por função, 6 no goleiro
  (30/15/10/15/20/10), percentil contra pares da mesma função → nota (P5=2,0 … P99=10), encolhimento pelos minutos,
  confiança %, desempenho × impacto separados, nota 10 rara, teto 9,5 com pouca cobertura, "não observado" sem tracking.
  Referência: `python -m src.analytics.rating_v2 --referencia 300` (cache em data/processed). Aba Jogadores com radar.
- ✅ Fortes e fracos: aba "📊 Todas as métricas (fora da curva)" — ~35 indicadores por jogador contra a mesma função,
  só o que está ≥ P85 ou ≤ P15; no modo equipe, o indicador mais fora da curva de cada titular (`outliers`).
- ✅ Próximo jogo: provável = 0,5 temporada + 0,35 últimos 5 + 0,15 último jogo (titular que faltou 1 jogo continua
  provável, marcado "dúvida"); suspensão por acúmulo de amarelos (`YELLOW_LIMIT`, conferir regra da competição);
  encaixe por posição real das escalações (LM/RM da ESPN corrigidos pela formação, `multi_fit`, encaixe ao cubo);
  escalação OFICIAL da ESPN substitui a provável (~1 h antes) e notícias que citam os clubes (`espn.preview`).
- ✅ Assistente: duas perguntas na mesma mensagem, "foi bom ou ruim?", quem merecia ganhar (xG/xT), principal criador,
  quem mais atacou as costas, quem menos marcou, jogador ausente explicado, respostas com abertura direta e "Em resumo".
- Limitação: abaixo da Série B não há fonte aberta acessível (OpenLigaDB é alemã; football-data.org grátis só Série A).

Rodada 5 (16/11/2026, 276 testes verdes):
- ✅ URGENTE posições: `src/squad/positions.py` — posição precisa × genérica por fonte (G/D/M/F da API-Football só diz o
  setor, não vira centroavante/zagueiro), LM/RM da ESPN pelo desenho, mesmo jogo de 2 fontes conta 1 vez, cadastro do
  Transfermarkt como desempate; `squad_from_db` usa a mesma regra. Era a causa de Yamal no meio e Koundé na zaga.
- ✅ Escalação: jogo HIPOTÉTICO contra qualquer time com escalação; campinho em pé (nota no círculo, anel de encaixe,
  sigla, nome em etiqueta); próximos jogos sem duplicar ESPN × FotMob; pré-jogo do rival com estilo e problemas recorrentes.
- ✅ Fonte FotMob (ver seção 6) + nota 2.0 por estatísticas (`src/analytics/rating_box.py`, régua própria
  `python -m src.analytics.rating_box --referencia 400`), mapa de chutes e notas na página de jogos sem lances, cartão
  do jogador estilo FC (qualidade, fase, regularidade).
- ✅ Assistente: por que venceu (`src/intelligence/match_story.py`: fatos → leitura → hipóteses), parar vários jogadores
  (fonte comum, ligação, corredor), estratégias pelo perfil medido (zona 14, profundidade, drible, condução, cruzamento,
  aéreo, proposição), perigo por critérios separados, goleiro/escalação direto, presença (banco/não relacionado),
  sprints só com dado físico real, pronome = jogador anterior, perguntas de substituição/placar/estilo/jogos parecidos.
  Disputa de pênaltis fora dos blocos táticos.
- ✅ Rodada 5 tática: `src/analytics/match_patterns.py` (bola parada, impacto das substituições — associação, não causa —,
  estado do jogo) e `src/analytics/team_history.py` (identidade com consistência, problemas que se repetem ≥4 jogos e
  ≥60%, pós-jogo × habitual, jogos parecidos); seção "🧩 Padrões e histórico" no jogo; aba "🧬 Estilo e tendências" no clube.
- ✅ `python -m src.machine_learning.benchmark`: na amostra da Copa (64 jogos) a regressão logística com distância/ângulo/
  passes (AUC 0,640) é estatisticamente MELHOR que a rede (0,623); zonas e placar quase não ajudam. Modelo em uso não
  foi trocado (decisão do usuário); painel nos Bastidores.
- Não feito: padrões ofensivos por sequência (terceiro homem etc.), perfil de treinador (fontes não trazem treinador de
  forma confiável), tracking/360 de outras ligas (não existe aberto), estaduais/Série D por notícia de escalação.

Rodada 6 (16/11/2026, 278 testes verdes) — correções pedidas com prints:
- ✅ Escalação: `canonical_names` (matchday) unifica o mesmo atleta entre fontes (Konaté/Konate, Van Dijk, Alisson ×
  Alisson Becker; dois "Gabriel" não se juntam) — acabou a "dúvida" falsa; quem não está no elenco atual sai mesmo com
  escalações velhas na base; "% das vezes que começou"; rival ≠ próprio time; pontos fortes/fracos de cada jogador em
  blocos verdes/vermelhos (`player_highlights`, temporada × mesma função); aviso de escalações velhas/ausentes.
- ✅ FotMob AUTOMÁTICA: thread `til-fotmob` (autosync.py) com o app aberto — calendário diário (1ª vez com
  FOTMOB_TEMPORADAS=2), jogos dos últimos 10 dias, histórico de 5 temporadas em lotes de 300; ~0,7 s por pedido
  (FOTMOB_INTERVALO); jogo sem dado não repete por 7 dias (`fotmob_tried`); status na barra do topo. ENABLE_FOTMOB=false
  desliga. Sob demanda: jogo sem detalhes busca a versão FotMob na hora; Escalação de time sem escalações recentes baixa
  os últimos 12 jogos. CLI `--only fotmob_tudo` (5 temporadas, tudo, retomável).
- ✅ Profundidade FotMob: `match_extra` (momentum, corredores de ataque, desfalques, craque); jogo sem lances ganha
  "O jogo pelos dados da FotMob" (`src/ui/pages/fotmob_depth.py`) e Fortes e fracos (`fotmob_strengths.py`); Assistente
  em jogo sem lances usa `src/intelligence/box_analyst.py` (ranking de qualquer número, nota, anular criador, como evitar
  gols, por que venceu, físico só se a liga mede); Comparar jogador × jogador pela FotMob.
- ✅ Classificação desenhada (escudo, faixas, últimos 5); linha do tempo sem "****" quando a fonte não traz o autor;
  erro `_detalhe` em Fortes e fracos (modo Equipe) corrigido.
- Pendente: erro do treino da rede nos Bastidores ("parou com erro") — pedir o texto do registro ao usuário.

Pendente / limitações honestas:
- Espanhol trava e páginas não traduzem inteiras (usuário pediu para deixar para depois).
- "Prováveis escalações por notícia" não existe em fonte aberta acessível: a provável vem dos últimos jogos; a oficial
  a ESPN publica ~1 h antes. Acúmulo de amarelos não é calculado (só vermelho no último jogo).
- Estaduais além de SP/RJ/MG/RS, Série D, feminino e base: fora da ESPN; avaliar football-data.org (responde daqui),
  OpenLigaDB (responde), RSSSF.
- F5/F6/F7 parciais; recalibrar `EXPECTED_PER90`; conferir no PC Understat e os experimentos B/A/C/D.

## 8. Ao final de cada sessão

Diga em poucas linhas o que mudou, quais comandos o usuário deve rodar (só os necessários) e o que ficou pendente.
Atualize a seção 6 e a seção 7 deste arquivo quando algo for baixado ou concluído.
