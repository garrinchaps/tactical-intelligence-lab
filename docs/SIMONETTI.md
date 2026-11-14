# Coletor do Simonetti Stats

`src/data_hub/sources/simonetti.py` · roda na sincronização diária (`python -m src.data_hub.sync --only simonetti lake`).

## Como funciona

O site monta as tabelas no navegador (JavaScript) a partir de arquivos de dados. Por isso o coletor:

1. lê a página inicial e os scripts dela, encontra os endereços dos arquivos de dados (JSON, xlsx ou CSV) e baixa
   **só esses arquivos** — poucas requisições por dia;
2. se não encontrar nenhum, faz uma varredura limitada das páginas internas e guarda qualquer tabela HTML
   (linhas deduplicadas por hash SHA-256, como no código original).

As tabelas vão para o lake (`data/lake/sm_*`), aparecem em **Catálogo & Dados → Base unificada** com filtros por
atleta, posição e clube, e entram no mapeamento `dim_players` / `dim_teams` com as outras fontes.

## Se a descoberta automática não achar os arquivos

1. Abra o site no Chrome, aperte **F12** → aba **Rede (Network)** → recarregue a página (F5).
2. No filtro, digite `json` (depois `xlsx`). Clique nos itens grandes e confira em **Resposta** se são os dados.
3. Copie o endereço (botão direito → *Copy* → *Copy URL*) e coloque no `.env`, separados por vírgula:

```
SIMONETTI_DATA_URLS=https://simonettistats.com.br/caminho/jogadores.json,https://simonettistats.com.br/caminho/times.json
```

## Conduta de coleta (por que difere do código sugerido)

| Código sugerido | Implementado | Motivo |
|---|---|---|
| User-Agent imitando o Chrome | User-Agent do projeto | o site sabe quem coleta e pode pedir para parar |
| 5 requisições simultâneas, varredura sem fim | 1 por vez, intervalo de 3 s, até 40 páginas | não sobrecarregar um site pequeno |
| sem `robots.txt` | respeita o `robots.txt` | regra básica de coleta |
| continua após erro | para ao receber 403/429 | o servidor sinalizou que não quer a coleta |
| `pd.read_html` em todas as páginas | arquivos de dados primeiro | o site é JavaScript: o HTML não tem as tabelas |

Ajustes no `.env`: `SIMONETTI_DELAY_S` (intervalo) e `SIMONETTI_MAX_PAGES` (limite da varredura).

## Uso dos dados

Os dados ficam só no seu computador (`data/` está no `.gitignore`); não publique as tabelas no GitHub nem em
outro lugar. Sobre a lei: o art. 8º da Lei 9.610/98 de fato não protege fatos e dados brutos, mas a mesma lei
protege bases de dados cuja organização seja criação intelectual (art. 7º, XIII) e dá ao titular da base o
direito sobre sua reprodução (art. 87). O site informa que usa provedores de estatísticas não identificados,
cujos contratos podem restringir a redistribuição. Coleta para pesquisa local, citando a fonte, é o uso mais
seguro; para publicar os dados, peça autorização pelo contato do site. (Isto não é orientação jurídica.)

## Sobre as sugestões de integração

* **Enriquecer o XGBoost com métricas do Simonetti:** o modelo de perigo trabalha com cada ação (passe/condução
  com coordenadas) de partidas da StatsBomb (Copa 2022); o Simonetti traz agregados de temporada do futebol
  atual. Não há partidas em comum, então juntar os dois no treino misturaria jogadores e épocas diferentes. O que
  já funciona: cruzar atleta a atleta pelo `dim_players` (ex.: métricas do Simonetti ao lado do valor de mercado
  do Transfermarkt e do xG do Understat).
* **GitHub Actions diário:** publicaria os dados coletados no repositório público. A atualização diária roda no
  seu computador (atualização automática do app e `scripts\agendar_atualizacao.ps1`), sem publicar nada.
