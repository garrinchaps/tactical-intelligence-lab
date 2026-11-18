"""
IA do laboratório (rodada 9) — o analista PRÓPRIO do Tactical Intelligence Lab.

Arquitetura clássica de geração de texto a partir de dados (data-to-text), toda nossa e treinável:
  1. facts.py      — transforma QUALQUER jogo (lances, estatísticas da FotMob/ESPN, números por jogador) em fatos:
                     valor, valor do adversário e régua da base (em quantos % dos jogos o número é maior);
  2. selector.py   — rede de seleção de conteúdo (regressão logística NumPy, treinada com as suas avaliações 👍/👎):
                     decide quais fatos merecem entrar na resposta, para a pergunta feita;
  3. writer.py     — redator: planeja a resposta (direta → números → leitura → como explorar → resumo) e escreve em
                     linguagem de futebol; as frases-modelo também aprendem com as avaliações (bandido de Thompson);
  4. engine.py     — junta tudo: responde o Assistente, escreve o relatório completo do jogo e registra o que mostrou
                     para o próximo treino.
Os números saem direto dos dados (nunca são inventados pelo redator). Nada é treinado sem rótulo: só respostas
avaliadas por você viram exemplo.
"""
