# Identidade tática de equipes, treinadores e modelos de jogo (rodada 22)

Código: `src/analytics/tactical_identity.py` · tela: `src/ui/identity_view.py` (página do time › 🧭 Identidade tática;
Escalação › pré-jogo › 🧠 Modelo de jogo do rival) · Assistente: intenção `_identity` em `src/intelligence/lab_ai/router.py`
· Scout: traços do modelo entram no encaixe tático e em "O modelo de jogo pede" · testes: `tests/test_day49_r22.py`.

## Princípios

- Duas camadas que nunca se misturam sem aviso: **lances com coordenadas** (StatsBomb/Wyscout/OpenPlay) e
  **estatísticas por jogo** (FotMob/ESPN). Cada número na tela diz de qual camada veio.
- Sem dados de rastreamento (tracking) **não** afirmamos linha de impedimento contínua, compactação ou distância entre
  linhas em cada instante — só **onde as ações aconteceram** (posição média de ações com bola e de ações defensivas).
- Aproximações são chamadas de aproximação (ex.: "PPDA aproximado"). Lacuna é lacuna.
- Toda dica de plano e de contratação traz a base (número, referência, nº de jogos).

## Matriz de implementação

| Pedido | Situação | Como é medido | Fonte | Limitação |
|---|---|---|---|---|
| Formação real por fase (com bola / sem bola) | ✅ novo | posição média de cada titular nas ações com bola × ações defensivas; linhas = quantos ficam até 9 jardas do mais recuado / do mais avançado (ex. 3-2-5) | lances | média do jogo, não foto de um instante |
| Saída com 3 (quem recua: volante entre zagueiros, lateral que fica, linha de 3) | ✅ novo | jogadores na linha mais recuada com bola + função da escalação | lances | idem |
| Laterais altos / por dentro | ✅ novo | x médio dos laterais × meias; distância da linha lateral | lances | idem |
| Saída de bola (goleiro curto × longo, do fundo ao último terço) | ✅ novo | passes do goleiro ≥ 40 jd; posses que nascem no terço defensivo e chegam ao último | lances | — |
| Progressão por corredor | ✅ novo | passes/conduções que terminam no último terço, pelo corredor (5 faixas) | lances | — |
| Último terço (cruzamentos, entradas na área) | ✅ novo (lances) / ✅ já existia (estatísticas) | contagem | lances / FotMob | — |
| Ritmo | ✅ novo | passes por posse | lances | sem velocidade de circulação real |
| Pressão alta / PPDA | ✅ novo | PPDA real = passes do rival no campo dele ÷ nossas ações defensivas ali; % de pressões no campo rival | lances | — |
| PPDA sem lances | ✅ novo (aproximação) | passes do rival no campo inteiro ÷ desarmes + interceptações + faltas | FotMob/ESPN | campo inteiro, não só o campo rival |
| Altura do bloco | ✅ novo | mediana do x das ações defensivas, em metros do próprio gol | lances | não é a linha defensiva medida |
| Bloco baixo / reativo | ✅ novo | posse e PPDA contra a média das mesmas competições | estatísticas | rótulo só com diferença clara |
| Transições (contra-ataques feitos e sofridos) | ✅ novo | finalização até 15 s após recuperação (nossa ou do rival) | lances | — |
| Identidade do treinador | ✅ novo | jogos separados pelo técnico da escalação; desenho mais usado e pontos por jogo por período | escalações | só quando a fonte traz o técnico |
| Consistência 1/3/5/10/20 jogos | ✅ novo | o rótulo de estilo aparece em quantos recortes | estatísticas | — |
| Casa × fora, vitórias × não vitórias | ✅ novo | mesmo perfil por recorte | estatísticas | por placar final, não por minuto |
| Contra fortes × fracos | ✅ já existia (Rankings/avaliação) | PageRank da competição | — | não repetido aqui |
| Contratação por função tática | ✅ novo | estilo → função pedida + métricas para medir | identidade | regras transparentes, não aprendidas |
| Oposição tática (plano contra o rival) | ✅ novo + ✅ já existia (Onde ganhar o jogo) | fase por fase, com a base | identidade | hipótese de trabalho |
| Fragilidades com hipóteses | ✅ já existia (`vulnerabilities`, `team_history`) | — | — | — |
| Visualizações | ✅ novo | campinho com posições médias por fase, cartões, corredores, tabela de recortes | — | — |
| Integração com o Assistente | ✅ novo | "como o X joga", "pressiona alto?", "como sai jogando?", "como enfrentar", "o que precisa contratar" | — | resposta sempre com a fonte |
| Velocidade, distâncias, compactação, linha de impedimento | ❌ não possível | exige tracking | — | nenhuma fonte aberta tem para o futebol brasileiro |

## Perguntas de exemplo

- "Como o Flamengo joga?" · "O Palmeiras pressiona alto?" · "Como o Bayern sai jogando?" · "Como enfrentar o Botafogo?"
- "Do que o Cruzeiro precisa contratar para o modelo de jogo?"
