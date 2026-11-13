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
| [football-data.org](https://www.football-data.org) | `FOOTBALL_DATA_TOKEN` | 12 competições, inclui Brasileirão Série A | grátis: só placares, 10 req/min |
| ESPN (feed JSON público) | `ENABLE_ESPN_PUBLIC_FEED=true` | jogos atuais de muitas ligas | **não oficial e desativado por padrão**. Use só para fins pessoais/acadêmicos, com baixa frequência, e confira os termos da ESPN |

### Sincronização e atualização automática

```bash
python -m src.data_hub.sync                      # todas as fontes habilitadas
python -m src.data_hub.sync --only statsbomb wyscout
python -m src.data_hub.sync --days 7 --prefetch-events 50
```

`--prefetch-events N` baixa os eventos das N partidas mais recentes que ainda não estão no banco. Isso alimenta a base de referência de *Pontos Fortes e Fracos*. A mesma sincronização tem um botão na seção **🗄️ Base de Dados**.

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
4. **Audita:** o `NumericHallucinationGuard` confere decimais, contagens e nomes de atletas. Se o Gemini citar algo fora das evidências, o texto é bloqueado e substituído.

Perguntas fora do tema (ex.: *"a coxinha é melhor que o hambúrguer?"*) recebem uma resposta curta de fora do escopo, nunca um relatório tático. O relatório completo só aparece quando pedido (*"relatório completo"*).

## 🖥️ Interface

- **Barra lateral:** busca, catálogo filtrável (fonte, nível, competição, temporada, time), upload de arquivo, cartão da partida aberta e equipe em foco.
- **Seções** (só a seção aberta é calculada):

| Seção | Conteúdo |
|---|---|
| 🏟️ Partida | placar, indicadores-chave, momento do jogo, comparativo, discrepâncias e diagnósticos. Em partidas de boxscore: estatísticas, linha do tempo, escalações e notas |
| 🧭 Tática | redes de passes (NetworkX), xT, clusters de perdas/recuperações e perigo de posse (XGBoost) |
| 👤 Jogadores | elenco e substituições, scout individual e comparador, pontos fortes e fracos por função |
| 📈 Clube | DNA longitudinal da equipe em várias partidas com eventos |
| 🧠 Analista IA | conversa com respostas recortadas e auditadas |
| 🗄️ Base de Dados | cobertura, fontes, cotas, sincronização e histórico |
| 🎥 Laboratório | demonstração de homografia (vídeo → campo 2D) |

## 🗂️ Estrutura

```
app.py                      # orquestração da interface (enxuto)
src/
  data_hub/                 # registro de fontes, SQLite, HTTP com cache/cota, busca, serviço, sync
    sources/                # statsbomb, wyscout, api_football, football_data, espn
  ui/                       # tema, componentes, contexto com cache, seletor de partidas
    pages/                  # match_center, tactics, players, club, ai_analyst, database, lab
  intelligence/             # compreensão da pergunta, evidências recortadas, analista dinâmico, NLP, Gemini
  reports/                  # pacote de evidências completo, guardião, relatórios MD/HTML
  ingestion/ preprocessing/ geometry/ metrics/ networks/ machine_learning/ tactical_engine/ visualization/
tests/                      # pytest (Dia 1 ao Dia 18) + fixtures
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
python -m src.data_hub.sync --only statsbomb wyscout
streamlit run app.py
```

O banco `database/tactical_lab.db` é criado e preenchido localmente e **não vai para o GitHub** (ele cresce com a sincronização).

## 🧪 Testes

```bash
pytest -q
```

## ⚠️ Limitações conhecidas

- **Sem tracking contínuo:** a "compactação" é estimada pela dispersão das ações defensivas (proxy declarada na resposta).
- **Wyscout:** não tem eventos de pressão (PPDA e retenção sob pressão ficam limitados), o xG é estimado (AUC ≈ 0,79 contra ≈ 0,83 do StatsBomb) e as posições são inferidas pela localização média.
- **Guardião:** confirma que cada número e cada nome existem nas evidências, mas não que pertencem àquela métrica específica.
- **Jogos atuais:** dependem de fontes com chave (API-Football paga para a temporada corrente) ou do feed não oficial da ESPN.

## 📊 Dados e créditos

- **StatsBomb Open Data**: qualquer pesquisa, análise ou conteúdo publicado deve citar a StatsBomb como fonte e usar o logo do [Media Pack](https://statsbomb.com/media-pack/).

  <a href="https://github.com/statsbomb/open-data"><img src="https://raw.githubusercontent.com/statsbomb/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png" alt="StatsBomb" width="220"></a>

- **Wyscout Public Dataset**: Pappalardo, L. et al. *A public data set of spatio-temporal match events in soccer competitions*. Scientific Data 6, 236 (2019). Licença CC BY 4.0. Conversão a partir do repositório processado por koenvo.
- **API-Football**, **football-data.org** e **ESPN**: dados sujeitos aos termos de cada provedor.
