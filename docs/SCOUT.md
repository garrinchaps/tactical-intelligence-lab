# Scout & Planejamento

## Objetivo

A Sala de Scout transforma o elenco e o histórico disponível do clube em um plano de mercado auditável. O módulo não tenta prever uma negociação como se tivesse acesso a conversas de agentes, salários privados ou orçamento aprovado. Ele combina evidência esportiva, referência de mercado, contexto competitivo e heurísticas explícitas.

## Dados utilizados

| Camada | Fonte local | Uso |
|---|---|---|
| Cadastro de mercado | \`tm_jogadores\` | Posição, idade, nacionalidade, clube cadastrado, contrato e valor de referência |
| Histórico de valores | \`tm_valores\` | Última avaliação disponível, média/variação dos últimos 12 meses |
| Histórico de jogos | \`match_player_stats\` + \`matches\` | Minutos, nota e estatísticas por jogo/temporada, até cinco anos |
| Escalações e treinador | \`match_lineups\` | Clube observado, posição em campo, técnico associado às partidas |
| Estatísticas de equipe | \`match_team_stats\` + \`matches\` | Diagnóstico recente do clube e referência por competição |
| Avaliações externas | tabelas \`sm_*\` aceitas por \`D.external_ratings()\` | Sinal secundário de avaliação, quando houver correspondência segura |

A cobertura depende do que já foi sincronizado. Uma base ausente não é substituída por número inventado. O dossiê mantém campos vazios e nível de confiança quando a evidência não existe.

### Reconciliação de elencos

O cadastro do Transfermarkt é cruzado com aparições recentes no banco de partidas. Se um jogador aparece por outro clube nos últimos 150 dias, o módulo pode exibir esse clube como **observado em campo**, preservando o registro do Transfermarkt em separado. Isso é um indício para auditoria, não prova documental de transferência.

O universo também pode incluir atletas que não estejam cadastrados na base de mercado quando há pelo menos quatro jogos e 450 minutos no período de 12 meses, com aparição nos últimos 180 dias e posição identificável. Para esses jogadores, idade, valor e contrato continuam desconhecidos.

Homônimos ambíguos são excluídos das recomendações automáticas em vez de receberem estatísticas de outro atleta.

## Qualidade esportiva por posição

A nota de qualidade (0–100) é calculada por percentis entre atletas da mesma função, utilizando indicadores diferentes por posição: goleiros, zagueiros, laterais, volantes, meias, pontas e centroavantes não compartilham a mesma régua. As estatísticas são normalizadas por 90 minutos quando aplicável.

A nota é retraída em direção a 50 quando a amostra de minutos ou a cobertura dos indicadores é pequena. O módulo mostra a confiança separadamente. Valor de mercado não entra na nota de qualidade esportiva.

Quando há avaliação externa correspondente e não ambígua, a nota final pode combinar 82% da nota estatística com 18% da avaliação externa. A nota externa isolada recebe confiança baixa e é identificada como tal.

## Diagnóstico do clube

A análise considera até 50 partidas recentes com resultado e nível de dados compatível, privilegiando a versão mais rica de um jogo duplicado. As médias a favor/contra são comparadas com jogos da mesma competição disponíveis na base, dentro de uma janela histórica aproximada de um ano.

As necessidades de posição combinam:
- produção/volume ofensivo ou defensivo abaixo/acima da referência competitiva;
- profundidade do elenco e qualidade observada por função;
- urgência calculada para priorizar as vagas.

Não é uma análise de vídeo nem de tracking. A identificação de fraquezas depende da disponibilidade e padronização de estatísticas por partida.

## Índice de Realismo da Transferência

O índice é heurístico, de 0 a 100, e combina:
- 30%: capacidade financeira proxy do comprador em relação à taxa aproximada;
- 18%: uso/minutagem recente do candidato;
- 16%: diferença de porte do elenco vendedor e comprador;
- 14%: prazo de contrato;
- 12%: afinidade linguística/cultural aproximada;
- 10%: fator neutro de contexto, antes de penalidades;
- penalidade adicional quando há risco de exceder a regra de estrangeiros identificada para a competição.

Contratos nos últimos seis ou doze meses podem reduzir a taxa aproximada. Jogadores com pouca utilização e qualidade elevada podem surgir como oportunidade de empréstimo. Ausência de informação sobre minutos não é interpretada como reserva.

A capacidade financeira é uma **faixa proxy**, estimada com taxas pagas conhecidas nos cinco anos anteriores e/ou valor do elenco titular. Não é orçamento oficial, não inclui salários, luvas, comissão, impostos, bônus ou concorrência entre clubes. A estimativa de taxa de transferência também não é uma cotação.

A nacionalidade é uma aproximação imperfeita de idioma e adaptação. Dupla nacionalidade conhecida é considerada; dados ausentes não recebem penalidade automática.

As regras de estrangeiros dependem de competição, temporada e definição regulamentar (por exemplo, atletas relacionados por partida versus inscritos). A regra brasileira configurada é identificada no código por temporada e deve ser confirmada contra o regulamento oficial de cada ano antes de uma decisão real. Outras competições permanecem sem limite presumido quando não há regra configurada.

## Compatibilidade tática e sinergia

A compatibilidade combina a qualidade do atleta com capacidades estatísticas coerentes com traços do clube (posse/construção, transição/verticalidade, amplitude/cruzamentos). Se há até cinco jogos do treinador atual no clube, o módulo procura partidas anteriores do mesmo técnico em outros clubes e mistura esses traços com o retrato observado do elenco atual.

A sinergia apresenta companheiros de setor e complementaridades posicionais/estatísticas. Sem dados de tracking, mapas de calor confiáveis ou eventos posicionais completos, ela é uma triagem explicável, não uma medição de movimentos sem bola ou química real.

## Ranking e feedback

A IA pré-filtra candidatos por função e calcula o ranking completo apenas para os candidatos mais promissores de cada posição, reduzindo custo por atualização de tela. O resultado combina qualidade, urgência do elenco, realismo financeiro, compatibilidade, sinergia e encaixe posicional.

Ao descartar um nome, o motivo e a rejeição são gravados localmente em \`scout_feedback\`. As próximas buscas usam motivos agregados e excluem jogadores anteriormente rejeitados, com uma opção para permitir que voltem ao radar. Esse feedback ajusta a priorização; ele não treina automaticamente os pesos de uma rede neural.

## Simulação, planejamento e exportação

A simulação executa o algoritmo de melhor XI já existente no projeto para a formação selecionada, antes e depois de adicionar um atleta ou retirar um jogador. As diferenças de médias individuais do XI são **projeções de composição**, não previsões de resultado nem garantia de que o desempenho coletivo aumentará na mesma proporção.

O plano permite marcar jogadores como ficam, saem ou são emprestados; as vendas usam deságio heurístico sobre o valor de referência. O plano pode ser salvo em \`scout_plans\` e exportado em Markdown ou PDF.

## Leituras importantes

- “Qualidade” significa desempenho estatístico relativo à posição, não reputação ou valor de mercado.
- “Realismo” é uma estimativa explicável, não probabilidade contratual calibrada com histórico de negociações.
- “Compatibilidade” e “sinergia” são indicadores de triagem enquanto não houver tracking e eventos posicionais para todos os atletas.
- Camisas/ uniformes de temporada não são atualizados por este módulo; o repositório não dispõe de uma fonte consolidada de kits licenciados.
- A disponibilidade de fotos de atletas depende de uma fonte de imagem confiável; onde não houver, a interface usa iniciais em vez de inventar uma foto.
- Antes de uma janela real, os dados de clube, contrato, nacionalidade, valores e regulamentos devem ser conferidos nas fontes oficiais mais recentes.
