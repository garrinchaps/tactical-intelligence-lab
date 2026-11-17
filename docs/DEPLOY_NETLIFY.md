# Deploy no Netlify

## Preparação versionada

O frontend futuro ficará em `apps/web`, com build `npm run build` e publicação em `dist` (configurado em `netlify.toml`, relativo ao base directory). Para SPA, usar redirect `/* /index.html 200`. Variáveis públicas devem conter somente URL/chave anon do Supabase e URL pública da API.

## Limitações

Netlify não mantém um processo FastAPI persistente. A API deverá ser hospedada separadamente em runtime Python gratuito, sujeito a suspensão/cold start. A configuração será adicionada somente quando o frontend existir e for validada com deploy de preview.

## Checklist manual do proprietário

1. Conectar o repositório GitHub ao Netlify.
2. Definir base directory e variáveis sem `service_role`.
3. Conferir HTTPS, preview e rota SPA.
4. Configurar URL da API e CORS.
5. Testar login, logout e uma consulta paginada externamente.
