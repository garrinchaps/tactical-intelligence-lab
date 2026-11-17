# Status da migração

Atualizado em 2026-11-17 — Fase 0/Fase 1 inicial.

## Resumo

| Área | Estado | Evidência |
|---|---|---|
| Branch e alterações locais | Preservadas | `git status`; `docs/COBERTURA.md` e `data/audits/` não foram revertidos |
| Auditoria estática | Concluída inicialmente | `data/audits/project_audit_fase0.json` |
| Banco principal | Íntegro | `PRAGMA quick_check = ok`, 42 tabelas, contagens registradas no inventário |
| Backup SQLite | Em execução na auditoria | `backups/audit-baseline-20261117/manifest.json` será a evidência |
| Testes baseline | 339 passed, 2 failed, 1 skipped | falhas reproduzíveis em `fetch_db` e teste obsoleto de clubes |
| Correção SQLite | Implementada | fechamento explícito em `_user_tables` e validação do download |
| Filtro de clubes | Teste atualizado | perfil carrega catálogo completo e filtra localmente |
| Decimal BR/US | Já aprovado nesta branch | não alterar metodologia; manter cobertura existente |
| Data Hub novo | Pendente | legado preservado |
| API/Web/autenticação | Pendente | depende das fases 2–4 |
| Publicação | Pendente | requer configuração externa e verificação |

## Inventário inicial

- 436 arquivos Python no escopo do auditor (inclui a cópia aninhada).
- 24 páginas Streamlit identificadas no app principal.
- 28 conectores/fontes em `src/connectors` e `src/data_hub/sources`.
- 42 arquivos de teste no diretório principal e 342 testes coletados com `pytest tests`.
- Banco principal: aproximadamente 4,87 GiB, preservado e ignorado pelo Git.

## Próximos passos

1. Confirmar manifest do backup.
2. Rodar suíte completa pós-correções.
3. Completar mapa funcional detalhado e documentação de licenças.
4. Implementar contratos/exportação do Data Hub sem tocar no banco legado.

## Atualização após estabilização

- Backup SQLite concluído e validado: `backups/audit-baseline-20261117/manifest.json`.
- Tag de restauração criada: `audit-baseline-20261117`.
- Suíte completa sequencial: **341 passed, 1 skipped, 20 warnings**.
- `duckdb>=1.0.0` instalado na venv e adicionado a `requirements.txt`; o skip será revalidado.
- Warnings de `DataFrame.drop(..., inplace=True)` removidos de `src/scout/engine.py` sem alterar a metodologia dos cálculos.
- Fase 0 e estabilização inicial: **concluídas com ressalvas**. O skip e a rotação da chave local ainda exigem fechamento.

## Fase 2 — início seguro do Data Hub

- Implementado `src/data_hub/artifacts.py` com manifesto JSON versionado, SHA-256, tamanho, formato, schema, proveniência, licença e flag explícita de redistribuição.
- Adicionados testes de manifesto e rejeição de artefato ausente: **2 novos testes passando**.
- O manifesto usa escrita atômica e não abre nem modifica o SQLite legado.
- Exportação de grandes tabelas e publicação em R2 ainda estão pendentes; nenhum dado restrito foi publicado.

## Validação acumulada

Após a API, autenticação inicial e exportação: **349 testes passaram, 0
falharam e 0 foram ignorados**. O tempo observado foi aproximadamente 161
segundos no ambiente local.

### Exportação seletiva

`src/data_hub/export.py` agora exporta uma tabela/seleção parametrizada em
chunks para `.csv.gz`, gera manifesto automaticamente e exige `pyarrow` para
Parquet. Identificadores são validados, o banco é aberto em modo read-only e
testes confirmam filtro, contagem e ausência de escrita no SQLite.

## Fase 3 — API inicial

- Criado `apps/api/main.py` com `/healthz`, `/readyz`, catálogo paginado e fontes.
- A API usa apenas consultas parametrizadas em modo SQLite read-only; não expõe credenciais nem conexão administrativa.
- Dependências `fastapi` e `uvicorn` adicionadas.
- Autenticação JWT/RBAC, objetos privados e Supabase ainda estão pendentes; nenhum endpoint protegido foi simulado.

### Autenticação inicial

`apps/api/auth.py` agora implementa validação JWT via JWKS, issuer/audience e
papéis `admin`, `analista` e `usuario`; `/api/v1/me` exige Bearer token. A
configuração real do projeto Supabase e testes com tokens emitidos continuam
pendentes, portanto nenhuma autenticação foi declarada operacional em produção.

## Fase 4 — shell web inicial

- Criado `apps/web` com React + TypeScript + Vite, dashboard de partidas, filtro de profundidade, estados de carregamento/erro e layout responsivo.
- Criados `netlify.toml` e redirect SPA; `node_modules`/`dist` estão ignorados.
- Build local do frontend foi executado com Node.js v26.13.1 e Vite 8.3.8; o deploy público ainda não foi declarado como verificado.
- Login, páginas completas e integração com todos os domínios ainda estão pendentes; o Streamlit continua preservado.

### Validação do build web

- Node.js `v26.13.1` instalado localmente.
- `npm install` e `npm run build` concluídos com sucesso usando Vite `8.3.8`.
- `npm audit --omit=dev`: **0 vulnerabilidades**.
- `npm audit` completo ainda acusa 5 vulnerabilidades altas em `picomatch`
  transitivo da ferramenta de build; não aplicar downgrade forçado sem release
  corrigida.

## Diretriz acadêmica integrada

- Criada `docs/MATRIZ_IA_ACADEMICA.md`, relacionando G00IIAR0.01 aos módulos atuais e futuros.
- O inventário distingue implementação existente de roadmap: ML supervisionado/não supervisionado, regras/guardrails e redes neurais já possuem bases no código; fuzzy formal, GA formal e RL ainda precisam de desenvolvimento e validação.
- O plano diretor foi atualizado para exigir dataset, split temporal, baseline, métricas, explicabilidade, licença e limitações antes de declarar qualquer pilar concluído.
- CNN, LSTM/GRU, autoencoder e RL permanecem P2 por dependerem de dados/ambientes ainda não comprovados; não serão apresentados como funcionalidades existentes.

## Entrega P0 — avaliação e model cards

- Criado `src/machine_learning/evaluation.py`: split temporal, isolamento por grupo, baseline majoritário, métricas de classificação, Brier/log-loss e matriz de confusão.
- Criado `src/machine_learning/model_catalog.py`: cards honestos dos modelos existentes, entradas, saídas, métricas e limitações.
- API: `GET /api/v1/models`.
- Web: seção `AI Lab` com modelos e limitações.
- Testes focados: **9 passed**.
- Build web: concluído com Vite 8.3.8; dependências de produção: `npm audit --omit=dev` sem vulnerabilidades.
- Próxima entrega somente após a suíte completa: otimização genética formal para planejamento de elenco, mantendo regras atuais como baseline.

## Entrega P1 — lógica fuzzy formal

- Criado `src/intelligence/fuzzy.py` com versão `mamdani-sugeno-v1`.
- Mamdani: fuzzificação triangular, regras SE–ENTÃO, agregação por máximo e defuzzificação por centroide discreto.
- Takagi–Sugeno: pesos de regras e consequentes lineares para índice contínuo de pressão territorial.
- API: `POST /api/v1/ai/fuzzy/player` e `POST /api/v1/ai/fuzzy/pressure`, com validação de faixas.
- Web: seção `Indicadores fuzzy` integrada ao dashboard, exibindo os índices e regras ativadas.
- Os contratos retornam `is_probability: false`; pertinência e índice fuzzy não são probabilidades.
- Testes fuzzy/API: **8 passed**; suíte completa: **359 passed, 0 skipped**.
- Limitações: os parâmetros atuais são experimentais; ainda falta replay retrospectivo, calibração contra rating legado e validação com dados ao vivo licenciados.
