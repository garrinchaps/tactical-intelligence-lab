# Deploy no Streamlit Community Cloud

## 1. Publicação inicial

1. Acesse https://share.streamlit.io/ e conecte sua conta GitHub.
2. Clique em **Create app**.
3. Selecione o repositório `garrinchaps/tactical-intelligence-lab`, branch `main`, arquivo principal `app.py`.
4. Em Advanced settings, use Python 3.11 se disponível.
5. Deploy.

## 2. Secrets

Se usar chaves de API, configure-as em **App settings → Secrets**, no formato TOML, por exemplo:

```toml
API_FOOTBALL_KEY = "..."
FOOTBALL_DATA_TOKEN = "..."
GEMINI_API_KEY = "..."
```

Não coloque chaves de API no GitHub.

## 3. Limitações e banco

O app usa SQLite em `database/tactical_lab.db`. No Community Cloud, o armazenamento local não é garantido como persistente entre reinicializações/redeploys. Não considere a instância publicada como banco de produção até configurar persistência externa ou backup/exportação.

A publicação inicial pode ser usada para validar o aplicativo e seus recursos com dados de demonstração. A migração do Data Hub SQLite para PostgreSQL/Supabase requer adaptação e testes; não é automaticamente feita por este deploy.

## 4. Recursos

A hospedagem gratuita possui limites de memória/CPU. Dependências e análises mais pesadas (XGBoost, SciPy, sklearn, gráficos e datasets maiores) devem ser testadas na instância. Se o app exceder os recursos, será necessário otimizar, limitar tarefas ou escolher hospedagem diferente.

## 5. Atualizações

A cada commit na branch configurada, o Community Cloud tende a reconstruir/atualizar o app automaticamente. Consulte os logs de build/runtime se o deploy falhar.
