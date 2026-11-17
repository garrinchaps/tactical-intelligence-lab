# Segurança e publicação

- `.env`, bancos, WAL/SHM, backups e dados brutos não entram no Git.
- Nunca usar `service_role` no frontend.
- API deve validar JWT, aplicar RBAC (`admin`, `analista`, `usuario`) e escopo por `user_id`.
- Supabase deve usar RLS para perfis, preferências, listas e relatórios privados.
- `apps/api/auth.py` valida Bearer JWT por JWKS do Supabase, issuer, audience e
  `sub`; papéis aceitos vêm de `app_metadata.role`.
- Consultas usam parâmetros; respostas são paginadas e limitadas.
- Rodar busca de segredos no working tree e no histórico antes de publicar; qualquer segredo histórico deve ser revogado/rotacionado.
- Logs devem redigir tokens, cookies, chaves e dados pessoais.
- `npm audit --omit=dev` está limpo; o audit completo ainda aponta um
  advisory upstream de `picomatch` usado apenas pela cadeia de build Vite.
  Não foi aplicado `npm audit fix --force`, pois ele propõe downgrade
  incompatível do Vite. O advisory deve ser reavaliado quando houver release
  corrigida.
- O banco principal foi acessado em modo somente leitura na auditoria; backup usa SQLite Backup API e quick check.
