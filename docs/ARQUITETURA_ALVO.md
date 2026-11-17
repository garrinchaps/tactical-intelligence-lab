# Arquitetura alvo

## Princípios

- O Streamlit/SQLite atual permanece como referência e rollback durante a migração.
- O frontend nunca acessa o SQLite nem credenciais administrativas.
- Coleta e atualização são processos do Data Hub, independentes da interface.
- Dados grandes ficam em Parquet particionado, consultados por DuckDB; Supabase guarda autenticação, metadados e objetos privados.
- Cada contrato possui versão, proveniência, licença e indicador de qualidade.

## Componentes

1. `data-platform/`: conectores, ingestão incremental/idempotente, normalização, validação, manifests e publicação seletiva.
2. `packages/intelligence/`: reaproveitamento de scout, ratings, planner, relatórios e inteligência tática.
3. `apps/api/`: FastAPI, serviços, contratos HTTP, JWT/RBAC e paginação.
4. `apps/web/`: React + TypeScript + Vite, sem segredos administrativos.
5. `infra/`: configurações versionáveis para Netlify, Supabase e R2.
6. Legado: `app.py`, `src/` e SQLite, mantidos até a paridade.

## Fluxo de dados

Fonte → conector com atribuição/licença → ingestão incremental → normalização/deduplicação → validação/proveniência → Parquet/DuckDB → API paginada/cacheada → frontend.

Atualizações pesadas não rodam no startup da interface. Cada execução grava fonte, início/fim, tentativas, contagens, erros e qualidade.

## Camada de IA

Os modelos ficam desacoplados das páginas e seguem contratos de dataset,
features, treino, inferência, avaliação e explicabilidade. O módulo de IA deve
exibir versão, entradas, métricas, baseline, limitações e proveniência. A
matriz acadêmica define a ordem: primeiro rastreabilidade e validação; depois
fuzzy/ML/otimização aplicados; por último visão, séries temporais, autoencoders
e RL quando houver dados e ambiente adequados.

## Limites conhecidos

- O SQLite local tem 5.232.553.984 bytes e não será enviado ao Postgres gratuito.
- O Netlify hospeda o frontend; FastAPI precisa de um runtime separado.
- Supabase/R2 e qualquer backend gratuito podem suspender, limitar armazenamento ou ter cold start. Isso será medido e documentado antes da publicação.
