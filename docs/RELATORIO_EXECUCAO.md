# Relatório de execução noturna — v27

Data: 14/11/2026 · base: v26 (commit `a7bac86`) · ambiente de execução: cópia de desenvolvimento do projeto
(Linux, Python 3.13, **sem acesso à internet**, sem httpx/duckdb/pyarrow instalados).

> Importante: este trabalho foi feito na cópia de desenvolvimento, não no seu computador. Tudo o que depende da
> sua máquina (backup da sua pasta `data/`, sincronizações reais, cobertura da sua base) ficou preparado com
> comandos prontos — ver **Pendências que exigem ação manual** no fim.

## Resultado dos testes

| momento | resultado |
|---|---|
| Etapa 0 — linha de base (v26) | **103 passaram, 1 pulado** |
| Etapa 7 — fechamento (v27) | **143 passaram, 3 pulados, 0 falhas** |

Nenhum teste existente regrediu. Os 3 pulados dependem de bibliotecas ausentes **neste** ambiente e devem rodar na
sua máquina: 2 precisam do `streamlit` (instalado aí), 1 precisa do `duckdb` (pula também aí se ele não estiver
instalado — é opcional). Um teste antigo era instável (falhava ~1 em 4 execuções porque o número "inventado" 977
às vezes existia de verdade na partida simulada); foi corrigido para escolher um número comprovadamente ausente.

Todas as páginas (Assistente, Jogos, Clubes, Jogadores, Comparar, Como a IA aprende, ML, Analista técnico, Dados,
Laboratório) abriram sem erro no teste de fumaça. A interface **não** foi vista num navegador real.

## Etapa 0 — Linha de base e proteção ✅

- `pytest`: 103 passaram, 1 pulado; `git status` limpo.
- Novo: `python -m src.tools.backup_local` copia `data/` e os bancos SQLite (pela API de backup do SQLite,
  consistente mesmo com o app aberto) para `backups/AAAAMMDD_HHMMSS/`, com instruções de reversão. `backups/`
  foi adicionado ao `.gitignore`. **O backup da sua pasta precisa ser feito por você** (passo 1 abaixo).

## Etapa 1 — Relatório de cobertura ✅

- Novo: `python -m src.data_hub.coverage` gera `docs/COBERTURA.md` direto do banco (consultas agregadas em SQL;
  1,8 s em 66 mil jogos, 4,5 s com a auditoria de qualidade). É regerado automaticamente ao fim de cada
  `python -m src.data_hub.sync`.
- Conteúdo: partidas por nível (EVENTOS / ESTATÍSTICAS / SÓ PLACAR), por fonte, por competição e temporada
  (com "eventos já em disco" e "estatísticas ausentes" em cada temporada), preenchimento de cada campo,
  inconsistências, qualidade de dados e últimas sincronizações.
- Inconsistência agora detectada e corrigida a cada sync: partida marcada ESTATÍSTICAS sem nenhum número é
  reclassificada como SÓ PLACAR (`reconcile_levels`).
- O `docs/COBERTURA.md` que vai neste pacote foi gerado na cópia de desenvolvimento (catálogo de demonstração:
  5.903 partidas, quase todas com eventos StatsBomb/Wyscout) e diz isso no topo. **A cobertura real da sua base
  só existe depois de rodar o comando na sua máquina.** Nenhum número foi estimado.

## Etapa 2 — Conectores e sincronização ✅ (com uma ressalva)

- Nova camada única de rede `src/data_hub/net.py`, usada por **todas** as fontes (antes, 9 conectores chamavam a
  internet por fora do cliente educado, sem repetição nem limpeza de chaves):
  - tempo-limite de **15 s** por operação;
  - repetição com **espera exponencial** (1 s, 2 s, 4 s…, teto 30 s) em 429/5xx/queda de rede, respeitando
    `Retry-After`; endereço inexistente/recusado para na 2ª tentativa;
  - **cache em disco** mantido nos conectores (ETag no Transfermarkt e nas fontes abertas; cache por URL nas APIs);
  - `redact()` em todas as mensagens de erro, no `sync_runs` do banco e no `data/sync_log.txt`: chaves do `.env`,
    chaves do Google, `Bearer …`, `key=`, `token=` e cabeçalhos de API nunca são gravados nem exibidos;
  - usa **httpx** quando instalado e cai para o `requests` (já presente) quando não — `httpx` foi adicionado ao
    `requirements.txt`.
- Cota diária: API-Football (100/dia) e agora também API-Futebol (`API_FUTEBOL_DAILY_QUOTA`, padrão 100) **param
  na primeira recusa**, com status `COTA` e o motivo registrado (antes, o laço seguia tentando liga por liga).
- ESPN continua sequencial, com 2 s entre chamadas (sem paralelismo).
- `python -m src.data_hub.sync` mantém `--only`, `--seasons`, `--rapido`; autoatualização 3 h / 24 h inalterada.
- **Ressalva honesta:** os conectores continuam **síncronos**. Foi criado `net.fetch_many()` (assíncrono com httpx,
  concorrência máxima 2), testado com um httpx simulado, mas não foi ligado às fontes: elas têm limites por
  minuto e regras de cortesia que tornam o paralelismo contraproducente. Não foi possível testar contra a
  internet real neste ambiente.

## Etapa 3 — Qualidade de dados e testes ✅

- Novo `src/data_hub/quality.py`:
  - bloqueia na gravação: placar negativo ou não inteiro, equipe vazia, mandante = visitante, data inválida,
    anterior a 1870 ou jogo encerrado com data futura (linhas rejeitadas vão para o log, as válidas seguem);
  - aviso (não bloqueia): data fora da temporada (`2023/24` → 01/06/2023–31/07/2024; `2024` → 01/01/2024–31/07/2025,
    para cobrir torneios adiados como a Euro 2020);
  - lances com minuto fora de 0–130 são descartados; eventos com minuto ou coordenada fora do campo
    (x 0–120, y 0–80) são contados na auditoria;
  - duplicatas por **SHA-256** do conteúdo normalizado (data, núcleo do nome das equipes, placar, competição):
    separa "duplicata" (mesma fonte, ids diferentes — erro) de "mesma partida em outra fonte" (ligação esperada).
- Identidades: `team_ids`/`player_ids` ganharam `confianca` (1,0 exata · 0,9 nome+clube · 0,8 nome longo↔curto ·
  0,6 só nome; fusões aproximadas de clubes = semelhança) e `revisar` (< 0,95); `dim_*` ganharam `confianca_min`.
- Pipeline DuckDB: corrigida incoerência — `lake.sql()` exigia nomes diferentes no DuckDB e no SQLite; agora
  `SELECT … FROM lake_<tabela>` funciona nos dois.
- Testes novos (42, em 4 arquivos `test_day24` a `test_day27`): parsers com amostras (football-data.co.uk completo e **com colunas ausentes**, API-Football,
  ESPN), domínio, duplicatas, identidades com confiança, ligação entre bases, DuckDB/SQLite, cobertura, backup,
  rede (backoff, Retry-After, redação, cota, lote assíncrono), proibição de `pyyaml`/`bs4` no código e no
  `requirements.txt` (os dois leitores opcionais de PyYAML foram removidos; vale sempre o leitor próprio).
- Resultado da auditoria na base sintética de teste (66 mil jogos): 119 jogos "time contra ele mesmo" e 14
  duplicatas — artefatos do gerador sintético, mas mostram que a auditoria pega esses casos.

## Etapa 4 — Analista e Verificador de Números ✅

- Novo `src/guard/present.py`, aplicado no Assistente e no Analista técnico: **cada número da resposta recebe
  `[EXATO]` ou `[DERIVADO]`**; frase ou linha de tabela com número **`[SEM ORIGEM]` não é exibida** e uma nota
  diz quantos trechos foram ocultados. Anos (1870–2100) não são métricas e ficam sem etiqueta. O texto original
  fica guardado em `report_raw`.
- Conferência em respostas reais do redator local (final da Copa 2022, 8 perguntas, incluindo o relatório
  completo com 264 números): **0 números sem origem, 0 trechos ocultados por engano.**
- Gemini: teto **rígido de 60 s para a resposta inteira** (cada tentativa recebe só o tempo que resta;
  configurável em `GEMINI_TIMEOUT_S`), salto de modelos que deram 404, memória do modelo que funcionou e
  retorno imediato ao redator local em qualquer falha — testado com um Gemini simulado.

## Etapa 5 — Motor neural de perigo ✅

- Validação **GroupKFold por `match_id`** (5 dobras × 2 sementes) dentro do conjunto de treino — testado que
  nenhuma partida aparece no treino e na validação da mesma dobra.
- Promoção só se, no **teste isolado** (partidas que nunca treinam), o ganho de log-loss sobre o campeão for
  **maior que σ entre dobras/sementes**, **≥ 0,0005** e com **IC 95% do bootstrap por partida acima de zero**.
  Um clone do campeão é rejeitado ("IC 95% inclui zero"); uma melhora clara é promovida (ambos testados).
- Toda tentativa (promovida ou rejeitada) vai para `models/registry/tentativas.jsonl` (só acréscimo) e para o
  histórico de versões, agora com σ, ganho e IC na página "Como a IA aprende".
- Custo: ~11 treinos por tentativa (0,3 s cada na amostra de 16 mil ações; ~2,5 s na base completa).

## Etapa 6 — Desempenho e interface ✅

- Busca de partidas na base de 66 mil jogos: **0,02–0,10 s** com cache e **~0,6 s** na primeira busca (o pior
  caso, que levava 2,9 s, era a deduplicação linha a linha — agora vetorizada e só sobre os melhores candidatos).
  Novo teste com 66 mil jogos sintéticos (limite com folga de 2 s para máquinas lentas).
- `st.cache_resource` (serviço/conexão) e `st.cache_data` (catálogo, partida, eventos, métricas) já estavam em
  uso; o filtro por time passou a usar a comparação rápida de nomes.
- Identidade visual verificada por teste: fundo `#090D16`, borda `#1E2A44`, `.fm-card`/`-blue`/`-red`,
  azul `#22D3EE`/`#3B82F6`, vermelho `#EF4444`, Space Grotesk + Inter; CSS começa com `<style>` e não tem linha
  em branco. Varredura de todas as páginas: nenhum bloco HTML com linha em branco (a causa do vazamento antigo).
- Estados vazios padronizados: "**Sem <dado> da fonte <nome da fonte> para esta partida**" + nível da partida
  (Resumo, Redes & xT, Jogadores, Fortes e fracos, Duas equipes) — conferido com uma partida da API-Football.
- Registro de fontes corrigido: openfootball e seleções constavam como nível ESTATÍSTICAS; são SÓ PLACAR.

## Etapa 7 — Fechamento ✅

- `pytest`: 143 passaram, 3 pulados, 0 falhas.
- Antes do commit: `git ls-files .env` → vazio · busca pelo prefixo das chaves do Google (o 2º comando
  obrigatório) → vazio · `git ls-files data/lake` → vazio. Nenhum `.db`, `data/`, `.env` ou `backups/` no
  commit. **Nenhum `git push` foi feito.**
- Duas ocorrências do prefixo foram encontradas e eliminadas antes da entrega: (1) o código de redação o escrevia
  literalmente — reescrito como `"AI" "za"`; (2) a primeira versão deste relatório citava o comando com o
  prefixo e entrou num commit local por falha minha de encadeamento (o commit não parou na checagem). O commit
  foi refeito (`--amend`, só local, nunca enviado) já sem a ocorrência. Nenhuma chave real esteve envolvida.

## Pendências que exigem ação manual

1. **Backup e testes na sua máquina** (comandos no fim): `python -m src.tools.backup_local`, depois
   `pip install -r requirements.txt` (instala o httpx) e `python -m pytest -q`. Esperado: cerca de 145
   passando, com 1 ou 2 pulados (o do DuckDB pula se ele não estiver instalado).
2. **Cobertura real:** rodar `python -m src.data_hub.sync --only fdcouk --seasons 10` (e as demais fontes) e
   depois `python -m src.data_hub.coverage`. O `docs/COBERTURA.md` deste pacote é só da cópia de demonstração.
3. **Arquivos em `data/` já versionados:** `data/demo/` (amostras públicas da StatsBomb, usadas no modo offline)
   e `data/processed/` (figuras e métricas de exemplo) estão no Git desde versões antigas. Nada novo foi
   adicionado, mas isso contraria a regra "nunca `data/` em commits". Decisão sua: manter (o modo offline
   depende de `data/demo/`) ou retirar do Git com `git rm -r --cached data/processed`.
4. **Conectores assíncronos:** ver a ressalva da Etapa 2 — se quiser mesmo paralelismo, diga quais fontes.
5. **Modelos antigos:** as versões da rede já salvas foram promovidas pela regra antiga; a regra nova vale a
   partir da próxima tentativa (as colunas novas aparecem vazias nas versões antigas).
6. **Olhar o visual no navegador** — não foi possível aqui.
