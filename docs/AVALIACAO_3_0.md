# Avaliação individual 3.0

## Objetivo

A nota final de 0 a 10 procura representar a qualidade da atuação, e não apenas a quantidade de ações com bola. O algoritmo mantém separados:

- **Desempenho-base:** produção estatística comparada com atletas de função semelhante.
- **Ajuste decisivo:** pontos somados ou subtraídos por eventos de impacto claramente identificados.
- **Nota final:** desempenho-base + ajuste decisivo, limitado à escala.
- **Confiança:** cobertura dos indicadores, minutos observados e tamanho da amostra de comparação.

O motor não tenta reproduzir as fórmulas proprietárias de Opta, SofaScore, Flashscore ou FotMob. Aproveita princípios públicos de avaliação por função, múltiplas dimensões e atualização por eventos, com pesos próprios e auditáveis.

## Conversão de percentil em nota

Cada indicador elegível é comparado com atuações da mesma função (ou de funções próximas quando a amostra é insuficiente). Indicadores negativos, como perdas e erros, têm o percentil invertido.

| Percentil | Nota |
|---:|---:|
| P0 | 3,0 |
| P5 | 3,8 |
| P10 | 4,5 |
| P25 | 5,5 |
| P50 | 6,4 |
| P75 | 7,4 |
| P90 | 8,6 |
| P95 | 9,25 |
| P99 | 10,0 |

Os pontos entre esses marcos são interpolados linearmente. A tabela é uma hipótese inicial de calibração do laboratório, não uma alegação de que as plataformas externas usam os mesmos valores.

## Pesos por função

As sete dimensões dos jogadores de linha somam 100%.

| Função predominante | Ofensiva | Criação | Progressão | Defesa | Eficiência | Disciplina | Trabalho coletivo |
|---|---:|---:|---:|---:|---:|---:|---:|
| Centroavante | 35 | 15 | 12 | 8 | 15 | 5 | 10 |
| Ponta | 27 | 18 | 20 | 10 | 12 | 5 | 8 |
| Meia ofensivo | 20 | 25 | 18 | 10 | 12 | 5 | 10 |
| Meia central | 14 | 22 | 20 | 17 | 12 | 5 | 10 |
| Volante | 8 | 15 | 15 | 32 | 12 | 8 | 10 |
| Lateral | 12 | 15 | 18 | 25 | 12 | 8 | 10 |
| Zagueiro | 5 | 10 | 10 | 40 | 15 | 10 | 10 |

Para goleiros há uma régua separada: defesa de finalizações (30%), posicionamento/leitura (15%), jogo aéreo (10%), distribuição (15%), decisões/segurança (20%) e cobertura (10%). Uma dimensão sem evidência fica como não observada e não recebe zero.

### Atuação em mais de uma função

Nos dados de eventos, o motor estima a mistura de funções usando a distribuição das posições anotadas nos eventos do atleta. Os pesos da avaliação são combinados proporcionalmente a essa mistura. A referência de pares também é ampliada para funções próximas quando uma parte relevante da atuação ocorreu em mais de um setor.

Isso é uma aproximação por eventos, não uma reconstrução minuto a minuto. Em partidas FotMob sem tracking, a posição do desenho tático é usada como função principal.

## Ajuste decisivo

O ajuste é deliberadamente limitado a **−1,5 a +2,5 pontos**:

- Gols sem pênalti: +0,48 cada; gols de pênalti: +0,30 cada quando a fonte distingue a cobrança.
- Quando a fonte não informa quais gols foram de pênalti, usa-se um peso intermediário de +0,42 por gol, sem inventar a distinção.
- Assistências: +0,35 cada, até +0,70.
- Gol que empata ou coloca a equipe à frente: +0,20, até +0,40.
- Goleiro: pênalti defendido na disputa +0,90 cada, até +1,50; defesa de alto impacto identificada pela heurística de chute no alvo com xG ≥ 0,25 a partir dos 85 minutos: +0,65 cada, até +0,90.
- Goleiro: gols evitados fornecidos pela fonte podem acrescentar até +0,45. Quando calculados pelo laboratório com xG pré-chute, são um proxy e não xGOT.
- Pênalti convertido na disputa: +0,10, até +0,30; perdido: −0,35, até −0,70.
- Grande chance desperdiçada: −0,45, até −0,90. Chute defendido pelo goleiro não é classificado como chance desperdiçada.
- Erro só é penalizado quando a fonte o marca explicitamente como causador de finalização ou gol: −0,80.
- Cartão vermelho: −0,60.

O resultado coletivo da equipe não gera bônus automático. O algoritmo não dá pontos apenas por vencer ou por não sofrer gols.

## Confiança e amostra

A confiança combina três fontes de evidência:

- Minutos observados: 35%.
- Cobertura das dimensões disponíveis: 35%.
- Tamanho da amostra de pares: 30%.

Menos de 15 minutos não recebe nota. Em amostras curtas, o desempenho-base é aproximado gradualmente da referência neutra 6,4. A nota final ainda pode receber ajuste por um evento decisivo observado.

Partidas sem estatísticas individuais do atleta ficam fora das médias recentes; ausência nunca equivale a nota zero. A qualidade recente exige ao menos três atuações com nota. A fase usa até as cinco atuações mais recentes disponíveis.

## Trabalho sem bola e limites da fonte

O motor considera pressão, ações defensivas, recuperações, participação na circulação, recepções entre linhas e sprints quando a fonte fornece esses registros.

Sem tracking óptico ou vídeo, não é possível afirmar que foram medidos fechamentos de linhas de passe, movimentos de atração, coberturas que não geraram ação registrada, liderança ou posicionamento preventivo. Essas ações devem aparecer como não observadas, em vez de receber bônus inventado.

## Duas réguas de referência

- **Partidas com eventos:** `src/analytics/rating_v2.py`, com eventos StatsBomb/Wyscout/OpenPlay e indicadores calculados a partir dos lances.
- **Partidas com estatísticas individuais sem coordenadas:** `src/analytics/rating_box.py`, com a base de pares da FotMob. Essa referência não é misturada com a régua de eventos, pois definições e cobertura de indicadores diferem.

Para reconstruir uma referência maior de partidas com eventos, comece com uma amostra moderada:

```powershell
python -m src.analytics.rating_v2 --referencia 100
```

Para reconstruir a referência das estatísticas individuais FotMob:

```powershell
python -m src.analytics.rating_box --referencia 200
```

Esses comandos gravam as referências em `data/processed/rating_ref_v2.parquet` e `data/processed/rating_ref_box.parquet`, respectivamente. São processos de construção de base; não precisam rodar a cada pergunta ou abertura da página. Quanto maior e mais representativa a amostra por competição e função, mais estáveis serão os percentis.

## Testes de aceitação adicionados

O teste da final da Copa do Mundo 2022 verifica:

- Mbappé e Messi acima do limiar mínimo esperado para a atuação;
- Emiliano Martínez identificado com pelo menos uma defesa de pênalti na disputa;
- nota final do goleiro superior ao desempenho-base quando há contribuição decisiva;
- desempenho-base e nota limitados à escala;
- dimensão de posicionamento do goleiro mantida como não observada quando não há dado;
- mistura de funções quando a atuação registra mais de uma posição.

Os testes foram adicionados ao conjunto automatizado, mas precisam ser executados no ambiente local para confirmar os resultados. A calibração também deve ser revista com amostra real ampla antes de tratar os pesos como definitivos.
