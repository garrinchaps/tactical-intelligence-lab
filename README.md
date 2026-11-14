# ⚽ Tactical Intelligence Lab

Plataforma de **ciência de dados aplicada ao futebol**: análise tática de partidas com redes de passes, Expected Threat (xT), machine learning, comparação contextual de atletas e um **analista de IA que responde exatamente ao recorte perguntado**, sempre auditado contra os dados.

> **Autores:** Matheus Pimenta Silva (Engenharia Elétrica, CEFET-MG) em colaboração com Pedro Magnani.

---

## 🗄️ Base de dados multi-fonte

O **Data Hub** (`src/data_hub/`) junta várias fontes num único catálogo SQLite. O **nível de dado** de cada partida fica sempre visível:

| Selo | Nível | Fontes | O que permite |
|---|---|---|---|
| ✅ **DADOS OFICIAIS REAIS — EVENTOS** | eventos com coordenadas | StatsBomb Open Data (~3.960 partidas), Wyscout Public Dataset (1.941 partidas) | tudo: redes de passes, xT, clusters, recortes espaciais |
| 📊 **DADOS REAIS — BOXSCORE** | estatísticas, escalações, linha do tempo | API-Football (chave), ESPN (opcional) | Match Center de boxscore, perguntas sobre números agregados |
| 📄 **DADOS REAIS — SOMENTE PLACAR** | placar e agenda | football-data.org (token) | catálogo e resultados recentes |
| ⚠️ **DADOS SIMULADOS** | gerados por modelo | gerador interno | só demonstração |

**Nenhum evento é inventado.** Quando a fonte não traz coordenadas, as seções espaciais avisam que estão indisponíveis, e a IA explica a limitação em vez de "reconstruir" passes.

### Fontes

| Fonte | Chave | Cobertura | Observações |
|---|---|---|---|
| [StatsBomb Open Data](https://github.com/statsbomb/open-data) | não | Copas do Mundo, Euros, Champions, La Liga (era Messi), Bundesliga 23/24, Premier 15/16, ligas femininas e outras | sincronização incremental: novas temporadas publicadas entram sozinhas |
| [Wyscout Public Dataset](https://github.com/koenvo/wyscout-soccer-match-event-dataset) | não | 5 grandes ligas 2017/18, Copa 2018, Euro 2016 | CC BY 4.0. Sem eventos de pressão; xG estimado pelo modelo do laboratório; posições inferidas |
| [API-Football](https://www.api-football.com) | `API_FOOTBALL_KEY` | +1.000 ligas, inclui Brasileirão A/B, Copa do Brasil, Libertadores | grátis: 100 req/dia (controladas). A temporada atual pode exigir plano pago |
| [football-data.co.uk](https://www.football-data.co.uk) | não | 16 ligas europeias (placar, 1º tempo, finalizações, no alvo, escanteios, faltas, cartões) desde os anos 1990; Brasileirão, Argentina, MLS, Liga MX e outras (placar) | CSVs gratuitos para download, com crédito. `--seasons 30` baixa o histórico completo |
| [football-data.org](https://www.football-data.org) | `FOOTBALL_DATA_TOKEN` | 12 competições, inclui Brasileirão Série A | grátis: só placares, 10 req/min |
| ESPN (feed JSON público) | `ENABLE_ESPN_PUBLIC_FEED=true` | jogos atuais de muitas ligas | **não oficial e desativado por padrão**. Use só para fins pessoais/acadêmicos, com baixa frequência, e confira os termos da ESPN |

### Sincronização e atualização automática

```bash
python -m src.data_hub.sync                      # todas as fontes habilitadas
python -m src.data_hub.sync --only statsbomb wyscout
python -m src.data_hub.sync --days 7 --prefetch-events 50
python -m src.data_hub.sync --only fdcouk --seasons 30   # histórico completo do football-data.co.uk
```

`--prefetch-events N` baixa os eventos das N partidas mais recentes que ainda não estão no banco. Isso alimenta a base de referência de *Pontos Fortes e Fracos*. A mesma sincronização tem um botão na página **🗄️ Catálogo & Dados**.

**Agendar todos os dias às 6h (Windows, PowerShell na pasta do projeto):**
```powershell
schtasks /Create /SC DAILY /ST 06:00 /TN "TacticalLabSync" /TR "cmd /c cd /d %CD% && venv\Scripts\python.exe -m src.data_hub.sync --days 3 --prefetch-events 20"
```

### Busca universal

Na barra lateral, a busca entende consultas como *"Argentina x França 2022"*, *"Leverkusen"*, *"Flamengo x Palmeiras ontem"*, *"Real Madrid x Barcelona da última rodada"* ou um ID. Ela procura no catálogo local e, se o jogo for recente, nas fontes online habilitadas. Quando a mesma partida existe em duas fontes, fica a mais rica (ex.: StatsBomb acima da Wyscout). Se a data pedida não existe, a busca sugere os confrontos reais entre as equipes.

## 🧠 Analista IA dinâmico

1. **Entende a pergunta** (`src/intelligence/query_understanding.py`): se é sobre futebol ou não, e qual o recorte (minutos, tempo, lado do campo, terço, fase, atletas, métricas, equipe-sujeito).
2. **Recorta as evidências** (`src/intelligence/scoped_evidence.py`): calcula só os blocos pedidos e, quando há janela de tempo, compara com o resto do jogo. *"Compactação defensiva do lado esquerdo no minuto 30"* gera apenas dados do lado esquerdo entre os minutos 25 e 35.
3. **Escreve a resposta:** com `GEMINI_API_KEY`, o Gemini redige do zero em estrutura livre. Sem chave, o redator local escreve só sobre os blocos calculados. A resposta sempre termina com um **resumo executivo**.
4. **Audita (guard v2, `src/guard/`):** cada número do texto é extraído (formato BR e US), comparado com as evidências e classificado como **EXATO**, **DERIVADO** (operação simples com unidade compatível), **CONSTANTE** metodológica ou **NÃO RASTREÁVEL**. Com algum não rastreável, o Gemini recebe uma segunda chance com contexto restrito; se falhar de novo, a resposta é **degradada e declarada** (redator local). A taxa de números não rastreáveis antes e depois fica registrada na tabela `guard_metrics`.

Perguntas fora do tema (ex.: *"a coxinha é melhor que o hambúrguer?"*) recebem uma resposta curta de fora do escopo, nunca um relatório tático. O relatório completo só aparece quando pedido (*"relatório completo"*).

## 🧾 Proveniência

Toda métrica exibida carrega um `ProvenanceRecord` (fonte, conector, licença, horário de ingestão, tier
**OFICIAL / DERIVADO / SIMULADO**, método). Os componentes da interface recusam número sem origem quando
`TIL_STRICT_PROVENANCE=1`, e cada página termina com o painel de proveniência. Detalhes, schema canônico e
decisões de projeto em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

## 🧪 Avaliação

`python -m src.evaluation.protocol` compara, com validação **por partida** (GroupKFold), uma baseline
majoritária, uma logística geométrica, o XGBoost e a rede neural própria; e testa se a betweenness ponderada
por xT supera o grau na rede de passes. Resultados e leitura honesta em [`docs/AVALIACAO.md`](docs/AVALIACAO.md);
validação com analistas humanos em [`docs/VALIDACAO_QUALITATIVA.md`](docs/VALIDACAO_QUALITATIVA.md).

## 🖥️ Interface

Navegação lateral agrupada; só a página aberta é calculada. Funciona offline com as partidas de `data/demo/`.

| Grupo | Página | Conteúdo |
|---|---|---|
| Partida | 🏟️ Centro da Partida | placar, KPIs com origem, momento do jogo, comparativo, boxscore quando não há eventos |
| Partida | 🕸️ Redes de Passes & xT | rede de passes, progressão de xT, grau × betweenness por xT |
| Inteligência Artificial | 🤖 Machine Learning & Inspeção | baselines, AUC por fold, importância, profundidade e ganho por split, matriz de confusão, K-Means com centróides, DBSCAN com eps/min_samples ajustáveis |
| Inteligência Artificial | 🧠 Rede Neural do Zero | treino ao vivo com hiperparâmetros, curva de perda, arquitetura, pais → filhos de cada neurônio |
| Inteligência Artificial | 💬 Analista IA | perguntas por recorte, classificação de cada número pelo guard, histórico da taxa |
| Jogadores, Clube e Comparações | 🆚 Comparações | as duas equipes lado a lado (indicadores, gols, destaques, redes de passes); a equipe contra ela mesma em outras partidas; jogador × jogador na partida ou somando várias partidas (totais e por 90 min) |
| Jogadores, Clube e Comparações | 👤 Jogadores · 📈 Clube · ⚖️ Pontos Fortes e Fracos | estatísticas individuais de todos os atletas (totais e por 90, exportáveis), elenco, dossiê, radar com n, tendências, percentis com “amostra insuficiente” |
| Dados | 🗄️ Catálogo & Dados · 🧪 Laboratório | fontes, sync, catálogo YAML, schema, upload de arquivos de scout; simulador de cenários com IC 95% e homografia |

Roteiro de apresentação: [`docs/APRESENTACAO.md`](docs/APRESENTACAO.md).

## 🗂️ Estrutura

```
app.py                      # navegação (st.navigation) e contexto da partida
config/competitions.yaml    # catálogo de competições (extensível por competitions.local.yaml)
data/demo/                  # partidas e amostra de treino para uso offline
data/templates/             # modelos de arquivo de scout (xT por zona, matriz de passes, métricas)
docs/                       # arquitetura, avaliação, validação qualitativa, roteiro
src/
  canonical/                # schema canônico + registro de proveniência
  connectors/               # StatsBomb, Wyscout, API, arquivos de scout, catálogo, bootstrap empírico
  data_hub/                 # SQLite, busca universal, sync
  guard/                    # extrator, ground truth, classificador, política, métricas
  evaluation/               # protocolo de avaliação e inspeção dos modelos
  machine_learning/         # XGBoost, clusters, dataset de perigo, rede neural NumPy
  ui/                       # tema, componentes, gráficos Plotly, contexto, páginas
  intelligence/ reports/ ingestion/ preprocessing/ geometry/ metrics/ networks/ visualization/
tests/                      # pytest (Dia 1 ao Dia 19)
```

## 🚀 Instalação

Requer **Python 3.10 ou superior**.

```powershell
git clone https://github.com/garrinchaps/tactical-intelligence-lab.git
cd tactical-intelligence-lab
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m src.data_hub.sync --only statsbomb wyscout   # opcional: sem isso o app abre as partidas de data/demo
python -m src.evaluation.protocol                       # opcional: gera o relatório de avaliação e os modelos
streamlit run app.py
```

O banco `database/tactical_lab.db` é criado e preenchido localmente e **não vai para o GitHub** (ele cresce com a sincronização).

## 🧪 Testes

```bash
pytest -q
$env:TIL_STRICT_PROVENANCE="1"; streamlit run app.py   # PowerShell: qualquer número sem origem vira erro
```

## ⚠️ Limitações conhecidas

- **Sem tracking contínuo:** a "compactação" é estimada pela dispersão das ações defensivas (proxy declarada na resposta).
- **Wyscout:** não tem eventos de pressão (PPDA e retenção sob pressão ficam limitados), o xG é estimado (AUC ≈ 0,79 contra ≈ 0,83 do StatsBomb) e as posições são inferidas pela localização média.
- **Guard:** confirma que cada número tem origem nas evidências (ou numa operação simples sobre elas), mas não que foi atribuído à métrica certa.
- **Modelos:** ganho marginal do XGBoost e da rede neural sobre a logística geométrica no alvo de perigo de posse; a betweenness por xT não supera o grau (ver `docs/AVALIACAO.md`).
- **Simulado:** o gerador por perfis tem PPDA calibrado, mas ainda poucos chutes e acerto de passe acima do real; o IC mede a incerteza do gerador.
- **Jogos atuais:** dependem de fontes com chave (API-Football paga para a temporada corrente) ou do feed não oficial da ESPN.

## 📊 Dados e créditos

- **StatsBomb Open Data**: qualquer pesquisa, análise ou conteúdo publicado deve citar a StatsBomb como fonte e usar o logo do [Media Pack](https://statsbomb.com/media-pack/).

  <a href="https://github.com/statsbomb/open-data"><img src="https://raw.githubusercontent.com/statsbomb/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png" alt="StatsBomb" width="220"></a>

- **Wyscout Public Dataset**: Pappalardo, L. et al. *A public data set of spatio-temporal match events in soccer competitions*. Scientific Data 6, 236 (2019). Licença CC BY 4.0. Conversão a partir do repositório processado por koenvo.
- **API-Football**, **football-data.org** e **ESPN**: dados sujeitos aos termos de cada provedor.
