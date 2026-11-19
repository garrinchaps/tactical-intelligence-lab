# Plano completo — Tactical Intelligence Lab público, 24 h, idêntico ao app

19/11/2026 · Documento para guardar e pedir a execução depois. Escrito sobre o que o projeto JÁ é (Streamlit +
SQLite + processo de fundo + parquet), sem mudar uma vírgula do que o app faz.

---

## 0. Decisões que definem tudo (resumo de uma página)

| tema | decisão | por quê |
|---|---|---|
| Site idêntico ao app | **publicar o PRÓPRIO app Streamlit** (o mesmo `app.py`), não reescrever em React | reescrever nunca fica idêntico; o React atual (`apps/web`) vira vitrine/API opcional |
| Onde roda | **um servidor (VPS) com disco próprio** — Hetzner CPX41/CCX23 (8 vCPU, 16 GB, 240 GB) ~€25–35/mês, ou Oracle Cloud "Always Free" ARM (4 vCPU, 24 GB, 200 GB) grátis | o banco tem vários GB e o processo de fundo baixa dados o tempo todo: precisa de disco local rápido e memória; Streamlit Community Cloud (1 GB) não comporta |
| Banco | **continua SQLite (WAL)** no disco do servidor + **réplica contínua** com Litestream para um bucket (Cloudflare R2/Backblaze B2, ~US$ 1–5/mês) | zero reescrita; um gravador (o worker) e muitos leitores (as telas) é exatamente o caso em que SQLite brilha; Litestream garante que nenhum dado se perde |
| Atualização 24 h | **o mesmo `src/data_hub/worker.py`** como serviço do sistema (systemd), separado das telas | já faz FotMob/ESPN/réguas/avaliações com prioridade baixa; no servidor ele roda sem o "modo leve" |
| Várias pessoas ao mesmo tempo | 2–3 processos Streamlit atrás de um proxy (Caddy) com "sticky session"; caches em disco compartilhados | cada visitante tem sua sessão; os cálculos pesados ficam guardados em disco e servem a todos |
| Domínio e HTTPS | Caddy (certificado automático Let's Encrypt) + domínio (.com.br ~R$ 40/ano) | sem configuração manual de certificado |
| Segurança | segredos só em variáveis do servidor (nunca no Git); Cloudflare na frente (cache, proteção contra abuso); login opcional | mesmas regras do CLAUDE.md |
| **Licenças (ponto crítico)** | ver seção 7: FotMob e parte das fontes são "uso pessoal" | publicar para todos sem cuidado pode violar termos; o plano tem 3 caminhos |

---

## 1. Arquitetura alvo (igual ao app de hoje, só que no servidor)

```
                 Internet ──► Cloudflare (DNS, HTTPS, cache, anti-abuso)
                                   │
                              Caddy (proxy, HTTPS automático, sticky)
                          ┌────────┼─────────┐
                    streamlit:8501  :8502   :8503     ← MESMO app.py (2–3 cópias, só leitura)
                          └────────┼─────────┘
                                   │ lê
        ┌──────────── disco do servidor (/srv/til) ─────────────────────┐
        │ database/tactical_lab.db  (SQLite WAL, ÚNICO gravador = worker) │
        │ data/processed/*.parquet  (avaliações, réguas, índice de busca)  │
        │ data/lake/ (parquet)  · cache do Streamlit em disco (persist)    │
        └─────────────────────────────────────────────────────────────────┘
                                   ▲ grava
                     worker (systemd): FotMob, ESPN, ao vivo, réguas, avaliações, Wikidata
                                   │
                     Litestream ──► bucket R2/B2 (réplica contínua, segundos de atraso)
                     backup diário completo + snapshot semanal fora do servidor
```

- **Telas** (Streamlit): `TIL_READONLY=1` (não grava no banco; ações que gravam viram pedidos para o worker numa
  fila), `AUTO_SYNC=false` (quem sincroniza é o worker), `TIL_MODO_LEVE=0`.
- **Worker**: um só processo gravando — evita "database is locked".
- **API** (opcional, já existe em `src/api`): FastAPI só leitura para o site React/vitrine e para integrações.

## 2. Banco de dados pronto e como ele cresce

1. **Montagem inicial no PC (já em andamento):** detalhes FotMob de Série A/B/C, Libertadores, Sul-Americana,
   sul-americanas e Europa (comandos da rodada 16), `python -m src.scout.evaluation`, Wikidata.
2. **Limpeza antes de subir:** `VACUUM` + `ANALYZE` + `python -m src.tools.criar_indices` (arquivo menor e consultas
   rápidas); conferir `docs/COBERTURA.md` e `docs/COBERTURA_JOGADORES.md`.
3. **Subida:** `rsync`/`rclone` do arquivo para o servidor (uma vez) — ou restaurar do bucket via Litestream.
4. **Daí em diante, o servidor é a fonte:** o worker atualiza 24 h; o PC passa a ser cópia de trabalho (baixa a réplica
   quando quiser: `litestream restore`).
5. **Crescimento previsto:** ~35 KB por jogo FotMob → 100 mil jogos ≈ 3,5 GB; com o resto da base, 8–15 GB em 2 anos.
   O disco de 200–240 GB sobra; SQLite aguenta centenas de GB.
6. **Particionar só se precisar:** jogos antigos (> 5 temporadas) podem ir para parquet no `data/lake` (DuckDB lê
   direto), mantendo o SQLite enxuto — a camada já existe (`src/data_lake`).

### Calendário do worker no servidor
| tarefa | frequência |
|---|---|
| jogos ao vivo (ligas com jogo rolando) | 1 min |
| calendário/resultados (FotMob/ESPN) | 3 h |
| detalhes dos jogos encerrados (FotMob, por recência) | contínuo, ~0,7 s por jogo |
| elencos atuais e lesões | 24 h |
| réguas (jogo típico, notas, confrontos) | 24 h |
| avaliações de jogadores + Wikidata | 24 h |
| índice de busca, PageRank | 24 h |
| `PRAGMA optimize`, checkpoint do WAL | 1 h |
| backup completo fora do servidor | 24 h (mantém 14) |

## 3. Publicação passo a passo (checklist executável)

1. Criar conta Hetzner (ou Oracle Free) → servidor Ubuntu 24.04, 16 GB+.
2. Usuário sem root, firewall (portas 22, 80, 443), SSH só com chave, `unattended-upgrades`.
3. Instalar Python 3.13+, `git`, Caddy, Litestream, `uv`/venv.
4. `git clone` do repositório no `/srv/til`; `pip install -r requirements.txt`.
5. Variáveis do servidor em `/etc/til.env` (fora do Git): `DATABASE_PATH`, `ENABLE_FOTMOB=true`, `AUTO_SYNC=false`
   nas telas, chaves de API se houver (nunca em código).
6. Subir o banco (seção 2) e os parquets.
7. Serviços systemd: `til-worker.service`, `til-web@8501..8503.service`, `litestream.service`.
8. Caddyfile: domínio → `reverse_proxy 127.0.0.1:8501 127.0.0.1:8502 127.0.0.1:8503 { lb_policy cookie }`
   (Streamlit precisa de sessão fixa por causa do websocket).
9. Cloudflare: DNS do domínio, proxy ligado, regra de cache para estáticos, limite de requisições por IP.
10. Monitoramento: Uptime Kuma (ou UptimeRobot grátis) pingando a página; painel "⏱️ Velocidade do app" (rodada 16)
    já mede cada tela; alerta por e-mail/Telegram se cair ou ficar lento.
11. **Entrega contínua:** GitHub Actions roda `pytest` em cada push; se verde no branch de produção, faz `ssh` no
    servidor → `git pull` → reinicia os serviços web um por vez (sem derrubar o site). O worker só reinicia se o
    código dele mudou.
12. Ensaio de desastre: apagar uma cópia de teste do banco e restaurar do bucket (`litestream restore`) — tem que voltar
    com segundos de diferença.

**Custo mensal estimado:** servidor €25–35 (ou grátis no Oracle) + bucket US$ 1–5 + domínio ~R$ 4/mês ≈ R$ 150–220
(ou ~R$ 30 no Oracle Free).

## 4. "Sem perder 1 dado nem 1 funcionalidade" — garantias

- **Mesmo código** nas duas pontas (PC e servidor): o site É o app.
- **Testes de paridade**: a suíte atual (438 testes) + um teste de fumaça que abre cada tela no servidor (Playwright,
  já usado aqui) depois de cada publicação.
- **Réplica contínua + backup diário + snapshot semanal** em outro provedor.
- **Gravação única pelo worker**; telas só leem → nada corrompe o banco.
- **Migrações por `user_version`** (já existem) rodam uma vez, no worker, antes das telas subirem.
- **Feature flags** por variável de ambiente para qualquer função cara (ex.: treino da rede) não travar o site público.

## 5. Velocidade com muita gente usando

- Caches pesados já estão em disco e valem para todos (rodada 15); versão de cache por time.
- Pré-cálculo noturno das telas mais abertas (times da Série A/B, competições principais) pelo worker.
- 2–3 cópias do Streamlit; cada uma com conexão SQLite reaproveitada (rodada 15).
- Treino de IA e "recalcular" ficam desligados no público (só para o administrador logado).
- Meta medida pelo monitor: 90% das telas < 2 s com cache quente.

## 6. Melhorias propostas por setor (ideias para as próximas rodadas)

**Dados**
- Wikidata (feito): nascimento/altura; ampliar para posição e clube formador.
- **SkillCorner Open Data** e **Metrica Sports sample** (tracking aberto de alguns jogos): demonstrar métricas físicas e
  de pressão de verdade nos Bastidores e no rating ("não observado" deixa de ser absoluto nesses jogos).
- **StatsBomb 360 novas liberações** e **Wyscout aberto** já integrados — automatizar checagem de novas versões.
- **ClubElo** (força de clubes europeus, CSV aberto) para calibrar o nível das ligas europeias — não respondeu daqui
  (DNS bloqueado neste ambiente); testar no PC/servidor.
- **football-data.org** (chave gratuita) para elencos/arbitragem nas ligas europeias; **OpenLigaDB** (Alemanha).
- **Transfermarkt (dcaribou)**: atualização semanal automática no worker.
- **Clima (Open-Meteo, aberto)** por jogo: chuva/calor como contexto de desempenho.
- **Eloratings** para seleções.

**Avaliação de jogadores (continuação da rodada 16)**
- Modelo de transferência entre ligas aprendido (feito: mínimos quadrados com regularização) — validar com jogadores que
  trocaram de liga na janela seguinte.
- Similaridade de perfil ("parecido com…") por vizinhos mais próximos dentro da função.
- Curva de idade por função (quando cada posição atinge o auge) para separar potencial de desempenho.
- Intervalo de confiança visível em toda nota.

**IA**
- O cérebro único (lab_brain) passar a ponderar também rankings e Scout pelo 👍/👎.
- Modelo de "probabilidade de titular no próximo jogo" (logística com uso recente, cartões, lesões) — validável jogo
  a jogo.
- Detector de anomalias (jogo fora do padrão de um time) com autoencoder simples — Q9 da matéria aplicada de verdade.

**Interface**
- Página do jogador unificada (ficha da rodada 16 + carreira + comparação), cartões no estilo do pré-jogo.
- Busca única com resultados instantâneos (índice em memória já existe) e atalhos de teclado.
- Modo celular: colunas que viram pilha, campinho vertical (já é), tabelas com rolagem horizontal.
- Exportar qualquer ficha/relatório em PDF.

**Operação**
- Painel "Saúde da base" público (cobertura por competição) — transparência sobre lacunas.
- Registro de mudanças (changelog) visível no app.

## 7. Licenças e termos — o que precisa ser decidido antes de abrir ao público

| fonte | situação para site público |
|---|---|
| StatsBomb Open Data | permitido com crédito ("dados: StatsBomb") — já creditado |
| Wyscout aberto, OpenPlay, openfootball, football-data.co.uk, Wikidata | abertos com crédito (CC/licenças próprias) |
| **FotMob** (JSON público do site) | **"uso pessoal e não comercial"** — redistribuir números brutos em site público é arriscado |
| **ESPN** (feed público) | termos de uso restritivos para reutilização pública |
| Transfermarkt via dcaribou | base derivada pública (CC0 no Kaggle), mas valores são do Transfermarkt — citar fonte |

**Três caminhos (escolha do Matheus):**
1. **Site com login para convidados** (professor, colegas): uso pessoal/acadêmico — menor risco, tudo funciona igual.
2. **Público só com métricas DERIVADAS** (notas, rankings, análises, gráficos) e sem tabelas brutas da FotMob/ESPN.
3. **Público completo** depois de pedir autorização/contratar dados (Sportmonks/API-Football pagos).

Recomendação: começar pelo caminho 1 (rápido, seguro, idêntico), evoluir para o 2.

## 8. Ordem de execução sugerida (quando pedir "execute o plano")

1. Preparar o banco final no PC (comandos de dados + avaliação + Wikidata + índices + VACUUM).
2. Modo somente leitura das telas (`TIL_READONLY`) e fila de pedidos para o worker.
3. Dockerfile/serviços systemd + Caddyfile + Litestream (arquivos no repositório, sem segredos).
4. Contratar servidor, publicar, apontar domínio, Cloudflare.
5. GitHub Actions (testes + publicação sem queda) e monitoramento.
6. Ensaio de restauração do backup.
7. Escolher o caminho de licença (seção 7) e liberar o acesso.
