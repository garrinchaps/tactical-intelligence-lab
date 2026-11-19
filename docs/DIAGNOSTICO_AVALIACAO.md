# Diagnóstico — como o Tactical Intelligence Lab avalia, compara e classifica jogadores

19/11/2026 · Escrito ANTES de mudar a metodologia, como pedido. Fontes do diagnóstico: o código atual
(`src/scout/engine.py`, `src/scout/traits.py`, `src/squad/matchday.py`, `src/analytics/rating_v2.py`,
`src/analytics/rating_box.py`, `src/squad/matchups.py`), o relatório de cobertura gerado no PC do usuário em 17/11
(`docs/COBERTURA.md`, 437 mil partidas) e as listas do Scout enviadas pelo usuário em 19/11.
Limite honesto: a cobertura POR JOGADOR (escalação, minutos, números individuais) não está no relatório de 17/11 — só a
de equipe. Por isso criei `python -m src.tools.cobertura_jogadores` (só leitura), que precisa rodar no PC do usuário
para fechar as lacunas marcadas com ❓ abaixo.

---

## 1. O que existe hoje

### 1.1 Fontes e níveis de dado (do relatório de 17/11)

| nível | partidas | o que permite |
|---|---|---|
| Lances com coordenadas | 32.449 (7%) | tática completa, xT, redes de passe, perigo por ação — só StatsBomb/Wyscout/OpenPlay (Europa, Copas; **nenhum jogo brasileiro**) |
| Estatísticas de equipe | 94.598 (22%) | estilo, fragilidades de equipe; com FotMob também números POR JOGADOR |
| Só placar | 310.300 (71%) | resultados, força de time (PageRank), nada individual |

Escalações existem em só **7%** das partidas. Números por jogador vêm quase só da FotMob (e um pouco da ESPN).

### 1.2 Competições pedidas

| competição | situação em 17/11 | causa |
|---|---|---|
| Brasileirão Série A 2025/26 | estatísticas em 100% (ESPN + FotMob) | ok; números por jogador dependem dos detalhes da FotMob ❓ |
| Brasileirão Série B 2025/26 | estatísticas de equipe em 100% (760 jogos/temporada) | **está na base**; o Scout não mostra porque o cadastro do Transfermarkt (dcaribou) não cobre a Série B e o atleta sem cadastro só entra com ≥ 4 jogos e ≥ 450 min de números POR JOGADOR — que ainda não foram baixados ❓ |
| Brasileirão Série C 2025 | 432 jogos, **100% só placar** | a ESPN não publica estatística da Série C; a FotMob tem a liga (id 8971), mas os detalhes não tinham sido baixados |
| Libertadores / Sul-Americana | não aparecem entre as 400 maiores linhas | poucos jogos com detalhe; a fila da FotMob priorizava Brasil/Europa (corrigido na rodada 15) |
| Argentina Liga Profesional 2025/26 | só placar (ESPN/fdcouk); FotMob só 2024 com estatística | temporadas 2025/26 da FotMob não estavam sincronizadas (o usuário rodou `fotmob_temporada --ligas sulamericanas` em 19/11) |
| Primera Nacional (ARG), Colômbia, Paraguai, Uruguai, Chile… | só placar | idem: calendário sem detalhes |

**Conclusão:** Série B e sul-americanas não "faltam na base" — faltam os DETALHES por jogo (escalação + números por
jogador), que só a FotMob fornece aberto. A Série C não tem estatística em nenhuma fonte acessível além da FotMob.

### 1.3 Como o ranking do Scout é construído hoje (`add_quality_scores`)

Uma nota ÚNICA de 0–100 por jogador:

```
desempenho = percentil (na mesma função, contra TODAS as ligas) de 5–9 métricas por 90 da FotMob
             × encolhimento pelos minutos  m / (m + 900)   [m = minutos do ano + 1/3 dos minutos antigos]
             × fator de nível = 0,5 + 0,5 × nível(45% valor do elenco do clube + 55% mediana da liga)
qualidade  = 0,6 × desempenho + 0,3 × reputação de mercado (valor atual ou 80% do pico de 3 anos) + 0,1 × nível
             (jovem ≤ 23 no topo do valor: reputação 0,45)
```

Mais: características (`traits.py`, percentil ≥ 85–90), precocidade e teto de potencial, nota externa (Simonetti) com
18% de peso, "confiança" = exposição × cobertura de métricas.

Em paralelo existem OUTRAS notas que não conversam com esta:
- **Escalação/Próximo jogo** (`matchday.player_table`): "qualidade 0–10" = titularidade + gols/assistências por jogo;
- **Nota 2.0 por estatísticas** (`rating_box`) e **nota 2.0 por lances** (`rating_v2`): percentil por jogo contra a
  mesma função, 6–7 dimensões;
- **Nota da FotMob** (importada, usada como métrica).

### 1.4 IA que participa (ou não) da avaliação de jogadores

| modelo | entra no ranking? | dados | validação |
|---|---|---|---|
| Rede de perigo (MLP) | **não** — só jogos com lances | 15 variáveis por ação | GroupKFold por partida, AUC ~0,60 |
| Seletor do Assistente (logística) | não | fatos do jogo | perguntas de validação |
| Características / precocidade | sim (exibição e teto) | percentis | **nenhuma** |
| `add_quality_scores` | é o ranking | percentis + mercado | **nenhuma validação contra resultado real** |
| Genético da escalação | usa a nota | nota × encaixe | comparação com o húngaro |

Não há hoje um modelo que APRENDA o que é um bom jogador; o ranking é uma fórmula de especialista sem validação.

---

## 2. Respostas às perguntas

**O que significa "ser um dos melhores da liga"?** Hoje o sistema mistura seis respostas diferentes numa nota só:
qualidade técnica (não medível com os dados abertos), produção por 90, desempenho na temporada, importância para a equipe,
potencial (parcialmente, via valor de mercado) e dificuldade dos adversários (só via nível do clube/liga).
**Sim, isso causa as injustiças das listas**, por estes mecanismos concretos:

| sintoma na lista do usuário | causa no código |
|---|---|
| Adryelson 76, Payet 74, Timo Hübers 78, Muniain 68 — **0 minuto** | minutos antigos ainda contam (1/3) + reputação/pico de valor (30%) + nível do clube (10%): quem não joga continua com nota alta |
| Darwin Núñez 84 (376 min), Messi 84 (335 min), Pedro Gonçalves 85 (452 min), James Maddison 83 (229 min) | o encolhimento por minutos só age sobre os 60% de desempenho; os 40% de reputação/nível ficam intactos |
| Reservas acima de titulares (Jefté 76 com 884 min; Luis Benedetti 71 com 438 min) | titularidade e % dos minutos da equipe **não entram** na nota |
| Neymar 86, De Bruyne 86, Lewandowski 84 com valor baixo | pico de valor + "domina a liga perde menos pelo nível" — reputação pesa mais do que a temporada |
| Tzolis com clube "Greece", Son "Korea Republic", Irankunda "Australia" | **defeito**: o reconhecimento de seleções só conhece poucos países (`national_team_key('Greece') == ''`), então o último jogo pela seleção vira "clube atual" |
| Zagueiros/volantes de time dominante baixos (Cubarsí) | métricas defensivas contam VOLUME sem ajuste pela posse do adversário |
| Ligas com mais métricas (Premier League com sprints, xG por jogador) favorecidas | percentil global misturando ligas com coberturas diferentes; métrica ausente reduz "cobertura" e encolhe a nota |
| Ligas de nível diferente no mesmo ranking | nível = valor de mercado do clube/liga (proxy), sem desempenho contra adversários fortes |

**O jogador merece estar no ranking? Quantos jogos, minutos, titularidades, entradas, % dos minutos da equipe?** Os
dados existem para jogos com escalação (FotMob/ESPN: titular × reserva, minutos), mas a nota do Scout só usa minutos.
Titularidades, entradas e % dos minutos da equipe **não são calculados** no Scout (existem só no Próximo jogo).

**Como evitar o reserva com poucos minutos acima do titular regular?** Separar "produção por 90" de "desempenho da
temporada" e exigir amostra mínima POR RANKING (ver etapa 2), com encolhimento bayesiano aplicado à nota INTEIRA, não a
60% dela.

**Comparar posições diferentes:** já há métricas por família (GK, CB, FB, DM, MID, ATT_MID, WIDE, ST), mas a POSIÇÃO vem
do cadastro (Transfermarkt) e não da FUNÇÃO exercida. Com as escalações (posição real no desenho, FotMob "layout") dá
para classificar a função por jogo (ex.: lateral construtor × lateral defensivo pelo perfil de ações) — ainda não feito.

**Dificuldade dos adversários:** existe ajuste parcial (`rating_ajustada`, `nivel_adversario` no histórico do Scout),
mas só sobre a nota da FotMob, e não separa "contra fortes" × "contra fracos". Com o PageRank de força dos times
(rodada 14) + jogos por jogador dá para medir produção por faixa de adversário — **viável com os dados atuais**.

**Contexto do time (protagonista ou time dominante?):** dá para calcular a fatia do jogador na produção da equipe (xG,
chances criadas, ações defensivas do time no mesmo jogo) — **viável com FotMob**; hoje não é usado.

**Pressão, movimentação sem bola, posicionamento:** **não medíveis** sem tracking (nenhuma fonte aberta para Brasil). O
sistema deve dizer "não observado" — já faz isso no rating 2.0; o Scout não.

---

## 3. Respostas sobre o próprio projeto

**Estatísticas que permitem avaliação confiável por posição (FotMob por jogador):**
- Atacantes/pontas/meias: gols, xG, chutes no alvo, xA, chances criadas, assistências, dribles certos, toques na área,
  passes no terço final — **boa cobertura**.
- Volantes/meias centrais: passes, acerto, passes que quebram linhas, recuperações, interceptações, desarmes, duelos —
  **boa**.
- Laterais: cruzamentos, chances criadas, ações defensivas, vezes driblado — **média** (sem corridas/sobreposição).
- Zagueiros: duelos aéreos, cortes, interceptações, bloqueios, passes longos, vezes driblado — **média** (falta
  posicionamento e defesa de área sem tracking).
- Goleiros: defesas, gols evitados (xGOT), erros — **média/fraca** (poucas métricas de saída e jogo com os pés).

**Posições avaliadas de forma injusta:** zagueiros e goleiros (métricas de volume, sem ajuste de posse); atacantes de
pressão/apoio (só gol/xG pesam); laterais construtores × defensivos (misturados).

**Competições a priorizar na expansão:** Série B e Série C (FotMob 8814, 8971), Libertadores e Sul-Americana (45, 299),
Argentina (112), depois Uruguai, Colômbia, Equador, Paraguai, Chile (todas já configuradas — falta baixar detalhes).

**Implementável já (com os dados atuais):** separar as avaliações; titularidade e % dos minutos da equipe; encolhimento
na nota inteira; amostra mínima por ranking; percentil por FAMÍLIA DE COBERTURA (comparar só quem tem as mesmas
métricas); produção contra adversários fortes × fracos (PageRank); casa × fora; regularidade (desvio entre jogos);
participação na produção da equipe; ajuste de posse para ações defensivas (posse da FotMob por jogo); seleções
reconhecidas (lista completa de países); "não observado" explícito.

**Precisa de novas fontes:** tracking (pressão, sem bola), lances com coordenadas do Brasil, transferências/valores da
Série B/C (Transfermarkt aberto não cobre), convocações de base.

**Modelos:** manter rede de perigo (só jogos com lances) e seletor do Assistente; **substituir** a fórmula única do
Scout por avaliações separadas; **criar** (a) modelo de transferência entre ligas — "quanto do desempenho na Série B
vira Série A" — estimado com jogadores que mudaram de liga dentro da base (mesmo atleta, antes × depois); (b)
similaridade de perfil (vizinhos mais próximos por função) para "parecido com…" e função tática.

**Como validar se ficou mais justo (critérios objetivos):**
1. *Estabilidade:* correlação da nota entre 1º e 2º turno do mesmo jogador (precisa subir).
2. *Poder preditivo:* nota da temporada T prevê nota/minutos em T+1 melhor que a atual (Spearman).
3. *Viés de cobertura:* depois de controlar desempenho, a liga/fonte não pode explicar a nota (teste com variável de
   liga; diferença média entre ligas de mesma força ≤ limiar).
4. *Sanidade:* 0 minuto no ano ⇒ fora dos rankings de desempenho; < 900 min ⇒ fora de "melhores da temporada"; reserva
   (< 40% dos minutos da equipe) nunca acima de titular com produção igual.
5. *Âncoras declaradas:* lista de controle (titulares indiscutíveis × reservas) usada só como teste, nunca como peso.

**Evitar amostra pequena:** encolhimento bayesiano para a média da FUNÇÃO na mesma liga em toda nota; minutos e
titularidades mínimos por ranking; intervalo de confiança mostrado.

**Evitar que a liga com mais dados domine:** percentil dentro de grupos de mesma cobertura; métrica ausente = não
avaliada (nunca zero nem penalidade); rankings por competição por padrão; ranking global só com ajuste de nível estimado
e marcado como estimativa.

---

## 4. Proposta em etapas (cada uma com critério de conclusão e testes)

**Etapa 0 — Dados (sem mudar nota).** Baixar detalhes FotMob de Série B/C, Libertadores, Sul-Americana, Argentina e
demais sul-americanas (fila já prioriza; comandos abaixo); corrigir seleções como "clube" (lista completa de países).
*Concluída quando* `cobertura_jogadores` mostrar Série B/Série C/Libertadores/Sul-Americana com ≥ 60% de jogos com
números por jogador nas temporadas 2025/26. *Testes:* seleção nunca vira clube atual; Série B aparece no Scout.

**Etapa 1 — Ficha de uso do jogador.** Jogos, minutos, titularidades, entradas, % dos minutos da equipe, sequência,
casa × fora, por competição. *Conclusão:* todo jogador do ranking mostra a ficha; *testes* com escalações sintéticas.

**Etapa 2 — Avaliações separadas (substitui a nota única, mantendo a coluna "qualidade" como "Avaliação geral").**
Desempenho por 90 · Desempenho da temporada · Regularidade · Impacto no time · Contra adversários fortes · Potencial ·
Custo-benefício · Revelação · Destaques por competição. Cada uma com amostra mínima e encolhimento próprio; reputação
de mercado sai do desempenho e fica só em potencial/custo-benefício. *Conclusão:* os 10 rankings na tela, com filtro por
competição (Série A/B/C separadas). *Testes:* critérios de sanidade da seção 3 automatizados.

**Etapa 3 — Função tática e contexto.** Função pela posição real nas escalações + perfil de ações (lateral construtor ×
defensivo, volante protetor × organizador, atacante de área × de apoio); ajuste de posse; fatia da produção da equipe.
*Testes:* função estável entre turnos; zagueiro de time dominante não penalizado pela posse.

**Etapa 4 — Força dos adversários e nível das ligas.** Produção por faixa de adversário (PageRank); modelo de
transferência entre ligas com jogadores que mudaram de liga (estimativa marcada como tal). *Testes:* validação cruzada
por jogador; intervalo de confiança.

**Etapa 5 — Ficha individual completa e validação.** Qualidades, deficiências, função ideal, time em que rende, estilos
de adversário, comparação com a função em outras ligas, tendência (evolução/queda), "não observado". Painel de validação
nos Bastidores (estabilidade, preditivo, viés de cobertura). *Conclusão:* métricas de validação melhores que a fórmula
atual; nada removido (rodar a suíte inteira).

**Interface/velocidade (em paralelo):** depois das etapas 0–2, padronizar o visual do Scout no estilo do pré-jogo
(cartões, campinho), ranking com abas por avaliação e ficha do jogador em uma página.
