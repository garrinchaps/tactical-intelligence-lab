# Bases públicas da comunidade (v29)

Origem: arquivo de conectores enviado pela usuária ("Camada de Ingestão Multi-Fonte v3"). Cada fonte foi
conferida na internet antes de entrar; o que mudou em relação ao arquivo está anotado.

| Fonte | Endereço real | O que entra | Nível | Licença / termos |
|---|---|---|---|---|
| Brasileirão 2003→ | github.com/adaoduque/Brasileirao_Dataset (o arquivo apontava outro usuário) | partidas, estatísticas por clube (chutes, no alvo, posse, passes, precisão, faltas, cartões, impedimentos, escanteios), gols e cartões por atleta/minuto | 📊 quando a linha de estatística não está zerada | GPL-2 segundo o Kaggle do autor; crédito à fonte |
| open-matchday | github.com/oladeeayo/open-matchday | temporada atual em dezenas de competições, placar do intervalo, minuto/autor dos gols, agenda (`agenda` no lake) | 📊 quando o football-data.co.uk tem o jogo; senão só placar | informativo, não comercial, sem revenda |
| Súmulas da CBF | github.com/BrazilianFootball/Data | ~11 mil jogos Série A–D e Copa do Brasil 2013–2025: placar, gols, cartões, árbitro, estádio | só placar (sem estatísticas de equipe) | MIT |
| OpenPlay | github.com/nlbair/openplay (dados nas *releases*, não é pacote `pip`) | eventos com coordenadas e xG em cada chute, grandes ligas e copas UEFA desde 2014/15 | ✅ eventos | CC BY 4.0 declarada, mas os eventos vêm de WhoScored/Opta e podem ser retirados a pedido dos donos — uso pessoal |

## Como cada uma funciona
* **Brasileirão** e **open-matchday**: baixados direto do GitHub (cache local; Brasileirão semanal, open-matchday
  a cada 12 h). Entram na atualização automática.
* **Súmulas da CBF**: na primeira sincronização o app baixa o repositório como .zip (sem git, sem conta) para
  `data/raw/cbf/` e extrai só `results/`. (Opcional: `CBF_DATA_PATH` apontando para um git clone.)
  O formato da pasta `results/` não é documentado; o leitor reconhece colunas por sinônimos.
  `python -m src.data_hub.sources.cbf_sumulas --inspecionar` mostra o que foi e o que não foi reconhecido.
* **OpenPlay**: na primeira sincronização o app consulta a API pública do GitHub, escolhe a release de dados mais
  nova (`data-…`), mostra o tamanho total e baixa os arquivos para `data/raw/openplay/` (ou `OPENPLAY_PATH`),
  retomando de onde parou se a conexão cair. `OPENPLAY_RELEASE=<tag>` fixa uma versão. O catálogo entra inteiro; os lances de um jogo são lidos só quando ele é aberto e ficam
  em cache. Coordenadas 0–100 viram 120×80. `python -m src.data_hub.sources.openplay --inspecionar` lista as
  tabelas e colunas. Formato real da release data-v0.1.0 (conferido no PC do usuário): a tabela por time só tem
  `team_id` + `side` (o nome vem da tabela de jogos); ~30 estatísticas por time entram no catálogo; posse fora de
  0–100 (existe no arquivo) é descartada; faltas, gols contra, substituições, cartões e disputa de pênaltis seguem
  as regras do WhoScored (ver `convert_events`); o placar dos eventos é conferido com o oficial. Conferido com a final da Copa 2022 reescrita no formato WhoScored: mesmos 1.263 passes,
  38 chutes, xG 11,3 e coordenadas idênticas após a conversão.

## Do arquivo original, o que foi aproveitado e o que não
* **Precedência por métrica e divergências nunca suavizadas** → `src/data_hub/consolidate.py` e o painel
  "🔀 Esta partida em N fontes" no Resumo do jogo.
* **FixtureConnector (agenda)** → agenda do open-matchday na tela do time ("📅 Próximos jogos").
* **UnderstatConnector** → o app já tinha um leitor completo do Understat (xG por jogo e por chute); mantido.
* **EmpiricalFallback** → não incorporado: `len(rng.integers(0, n, size=n))` é sempre `n`, então o "bootstrap"
  devolvia intervalo de largura zero. O app já tem simulação com intervalo de confiança real.
* **requests / beautifulsoup4 / pacote `openplay`** → não usados (regra do projeto: sem bs4; rede pela camada
  `src/data_hub/net.py`).

## O que não foi possível testar aqui
A cópia de desenvolvimento não tem internet: os leitores foram testados com amostras montadas exatamente no
formato documentado de cada fonte. Na primeira sincronização na sua máquina, se alguma coluna vier com outro
nome, o comando `--inspecionar` (CBF, OpenPlay) ou a mensagem de erro (Brasileirão) dizem qual.

## Base completa num comando
`python -m src.data_hub.sync --tudo` roda, nesta ordem: StatsBomb, Wyscout, football-data.co.uk (desde 1993/94),
openfootball, seleções, Brasileirão, open-matchday, OpenPlay, súmulas da CBF, ESPN (recentes e histórico desde
2018), API-Football, football-data.org, API-Futebol, Base dos Dados, Transfermarkt, Understat (desde 2014/15),
Simonetti e a ligação entre fontes. Fontes sem chave ou flag no `.env` são puladas e avisadas.

## Opção "Só partidas reais"
Ao lado da caixa de busca. Ligada (padrão): simulações e arquivos enviados não aparecem na busca, no Assistente nem
nas telas de time e competição.
