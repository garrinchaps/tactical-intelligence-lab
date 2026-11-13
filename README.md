# ⚽ Tactical Intelligence Lab

Plataforma de **ciência de dados aplicada ao futebol**: análise tática de partidas a partir de dados de eventos, com redes de passes, Expected Threat (xT), machine learning, comparação contextual de atletas e relatórios gerados por IA com **auditoria anti-alucinação**.

> **Autores:** Matheus Pimenta Silva (Engenharia Elétrica, CEFET-MG) em colaboração com Pedro Magnani.

---

## ✨ O que o app faz

O app (Streamlit, dark mode) é organizado em 7 páginas:

| Página | Conteúdo |
|---|---|
| **1. Match Center & Momento Tático** | Placar, xG, posse, PPDA, Field Tilt, linha do tempo de momento e diagnósticos causa-efeito |
| **2. Redes de Passes & xT** | Rede de passes (NetworkX) com betweenness e PageRank, mapas de progressão por xT |
| **3. Machine Learning & Risco** | Clusters de perdas (K-Means), núcleos de recuperação (DBSCAN) e perigo de posse (XGBoost + Regressão Logística) |
| **4. Scout, Elenco & Substituições** | Matriz de profundidade, relatório individual, comparador head-to-head e sugestões de substituição pós-minuto 60 |
| **5. DNA Longitudinal & Vídeo 2D** | Tendências crônicas em várias partidas e demonstração de homografia (vídeo → campo 2D) |
| **6. Pontos Fortes e Fracos** | Percentis contextuais do atleta (por função, por 90 min) ou da equipe contra uma base de partidas reais, radar e interpretação |
| **7. Central de IA & Relatórios** | Perguntas em linguagem natural → relatório tático auditado, exportável em Markdown e HTML |

## 🛡️ Transparência e auditoria

- **Dados simulados são sempre sinalizados.** As partidas do catálogo do Brasileirão (IDs `880001`…) e as simulações sob demanda são **geradas por modelo probabilístico**, não são jogos reais. O app e todos os relatórios exibem o selo `⚠️ [DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA]`, e essas partidas nunca entram na base de referência.
- **Guardião anti-alucinação** (`NumericHallucinationGuard`): todo texto (da IA ou do motor local) é conferido contra o pacote de evidências calculado. São checados:
  - decimais e percentuais;
  - contagens inteiras (passes, finalizações, perdas, minutos…);
  - nomes de atletas, que precisam estar no elenco da partida.

  Se qualquer item não for encontrado, o texto do Gemini é **bloqueado** e substituído pelo relatório determinístico local.
- **Rigor estatístico:** diferenças entre taxas são expressas em **pontos percentuais (pp)** e acompanhadas do tamanho da amostra (N) e do grau de evidência (FORTE / MODERADA / LIMITADA).

## 🗂️ Estrutura

```
app.py                         # interface Streamlit (7 páginas)
database/schema.sql            # schema SQLite (foreign keys ativas)
src/
  ingestion/                   # StatsBomb Open Data + cache, catálogo, gerador SIMULADO
  preprocessing/               # limpeza de eventos e cadeias de posse
  geometry/                    # zonas do campo, corredores, convex hull
  metrics/                     # métricas táticas, xT, avaliação de atletas, pontos fortes/fracos
  networks/                    # redes de passes (NetworkX)
  machine_learning/            # K-Means, DBSCAN, XGBoost
  tactical_engine/             # diagnósticos causa-efeito
  intelligence/                # roteador NLP (MLP) e analista generativo (Gemini)
  reports/                     # pacote de evidências, guardião, relatórios MD/HTML
  visualization/               # gráficos de campo e página de pontos fortes/fracos
tests/                         # suíte pytest (Dia 1 ao Dia 17)
```

## 🚀 Instalação

Requer **Python 3.10 ou superior**.

**Windows (PowerShell)**
```powershell
git clone https://github.com/garrinchaps/tactical-intelligence-lab.git
cd tactical-intelligence-lab
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

**Linux / macOS**
```bash
git clone https://github.com/garrinchaps/tactical-intelligence-lab.git
cd tactical-intelligence-lab
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Chave do Gemini (opcional)

Sem chave, tudo funciona com o **motor determinístico local**. Para usar a IA generativa, gere uma chave gratuita no [Google AI Studio](https://aistudio.google.com/) e coloque no arquivo `.env`:

```
GEMINI_API_KEY=sua_chave_aqui
```

⚠️ O `.env` está no `.gitignore` e **nunca** deve ser enviado ao GitHub.

## ▶️ Executar

```bash
streamlit run app.py
```

Na primeira vez que a página **Pontos Fortes e Fracos** for aberta, a base de referência é montada a partir das partidas reais salvas no banco local (cerca de 20 segundos) e guardada em `data/processed/reference_baselines.json`.

## 🧪 Testes

```bash
pytest -q
```

## ⚠️ Limitações conhecidas

- Os dados de eventos não têm tracking contínuo nem GPS: métricas de fadiga e de espaço sem bola são aproximações.
- O guardião confirma que cada número **existe** nas evidências da partida, mas não que pertence àquela métrica específica.
- O gerador simulado produz poucas ações defensivas. Por isso o PPDA das partidas simuladas sai fora da faixa real.
- A base de referência depende das partidas reais armazenadas localmente (hoje, 18 jogos de elite do StatsBomb Open Data). Os percentis devem ser lidos como comparação com essa amostra.

## 📊 Dados e créditos

Os dados de eventos reais vêm do **[StatsBomb Open Data](https://github.com/statsbomb/open-data)**, disponibilizado gratuitamente pela StatsBomb (Hudl).

<a href="https://github.com/statsbomb/open-data"><img src="https://raw.githubusercontent.com/statsbomb/open-data/master/img/SB%20-%20Icon%20Lockup%20-%20Colour%20positive.png" alt="StatsBomb" width="220"></a>

Conforme o repositório oficial, qualquer pesquisa, análise ou conteúdo publicado com esses dados deve citar a **StatsBomb como fonte** e usar o logo disponível no [Media Pack](https://statsbomb.com/media-pack/) da empresa.
