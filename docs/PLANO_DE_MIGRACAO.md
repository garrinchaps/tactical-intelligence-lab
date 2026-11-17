# Plano de migração incremental

## Fase 0 — Auditoria (em execução)

- Inventariar páginas, símbolos, conectores, testes, dependências e banco.
- Verificar branches/PRs e preservar alterações locais.
- Criar backup SQLite verificável e ponto de restauração Git.

## Fase 1 — Estabilização

- Corrigir fechamento efetivo de conexões SQLite no Windows.
- Corrigir testes obsoletos sem alterar a regra funcional de filtros.
- Fixar comando de testes e registrar baseline.
- Adicionar verificações de segredos, arquivos grandes e integridade.

## Fase 2 — Data Hub

- Definir schemas e manifests versionados.
- Exportar somente tabelas/dados autorizados para Parquet particionado.
- Consultar Parquet via DuckDB e comparar amostras/contagens com SQLite.
- Criar jobs incrementais, idempotentes e observáveis.

## Fase 3 — API

- Expor serviços de leitura seletiva, busca, scout, clubes, jogadores, partidas e relatórios.
- Validar JWT e RBAC; isolar objetos privados por usuário.
- Manter o caminho legado até testes de paridade.

## Fase 4 — Web

- Criar shell React/Vite e autenticação Supabase.
- Migrar páginas por domínio, preservando filtros e estados vazios/indisponíveis.
- Executar testes de contrato, integração e e2e.

## Fases 5–8 — Infraestrutura, paridade e publicação

- Configurar Netlify, runtime FastAPI, Supabase, R2 e CI sem cartão/serviço pago.
- Medir latência/cache e comparar resultados conhecidos.
- Publicar somente código/dados licenciados; manter rollback do legado.

Nenhuma fase é considerada concluída apenas por estrutura criada: exige implementação, teste e evidência registrada em `STATUS_DA_MIGRACAO.md`.
