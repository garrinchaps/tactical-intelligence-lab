# Referências visuais e evolução da interface

**Projeto:** Tactical Intelligence Lab  
**Data de registro:** 17 de novembro de 2026  
**Origem:** cinco referências visuais fornecidas na conversa do projeto.

Este documento transforma as cinco referências em requisitos de produto e interface. Elas são inspirações de organização e visualização, não dados reais nem especificações para copiar literalmente. Nomes, clubes, valores, métricas e placares exibidos nos mockups não devem ser tratados como informação do banco.

## Princípios de implementação

1. **Preservar o que já funciona.** As telas e os fluxos existentes continuam sendo a base. Novas capacidades devem ser adicionadas de forma incremental, preferencialmente por componentes reutilizáveis ou abas novas, sem substituir páginas inteiras.
2. **Não simular cobertura inexistente.** Um gráfico só aparece quando há dados suficientes. Ausência de tracking, salário, valor de transferência ou evento deve ser mostrada como “não disponível/não observado”, nunca como zero ou dado inventado.
3. **Separar observado de estimado.** Estatísticas registradas, métricas calculadas pelo laboratório e previsões devem ter identificação visual e metodológica distinta.
4. **Mostrar procedência e amostra.** Exibir fonte, período, competição, minutagem, número de partidas e confiança quando forem relevantes para interpretar o indicador.
5. **Não bloquear a aplicação.** Carregar painéis sob demanda, reutilizar cache, executar sincronizações e cálculos pesados fora do ciclo de renderização e medir a latência antes/depois.
6. **Manter consistência visual.** A maioria das referências usa tema escuro. A referência de finanças usa tema claro; ela deve inspirar a hierarquia e a organização dos dados, não impor uma troca global de tema. Os componentes devem respeitar o tema já adotado pelo aplicativo.
7. **Não introduzir dependência pesada sem benchmark.** Preferir componentes e bibliotecas já existentes. Qualquer nova dependência precisa justificar manutenção, peso e ganho mensurável.

## As cinco referências convertidas em requisitos

### 1. Painel geral de desempenho e análise da equipe

**O que a referência demonstra**
- Faixa superior com indicadores-chave em cartões compactos.
- Painel tático do campo com posições, movimentos e zonas.
- Mapa de calor individual.
- Gráfico de posse.
- Comparação de produção ofensiva e resultados.
- Radar para comparar dimensões físicas/técnicas.

**Aplicação no Tactical Intelligence Lab**
- Criar uma visão geral de equipe/partida que reúna apenas indicadores disponíveis no recorte selecionado.
- Permitir trocar equipe, partida, competição e período sem reconstruir todo o histórico.
- Ligar cada indicador a uma definição e à origem dos dados.
- Usar mapas de calor apenas quando existirem coordenadas/eventos adequados; não inferir tracking a partir de estatísticas de boxscore.

**Ponto de integração sugerido:** páginas de clubes, partidas, redes e visualizações já existentes. Confirmar o fluxo atual antes de escolher a tela definitiva.

### 2. Gestão de elenco, salários e transferências

**O que a referência demonstra**
- Resumo financeiro do clube.
- Lista de atletas com custo salarial.
- Entradas e saídas de transferências.
- Próximas movimentações.
- Gráficos de evolução dos valores.

**Aplicação no Tactical Intelligence Lab**
- Separar valor de mercado, valor de transferência, salário e orçamento: são conceitos diferentes e não devem ser somados ou comparados como se fossem equivalentes.
- Exibir histórico de transferências com clube de origem/destino, tipo de operação, data, moeda, valor e fonte quando disponíveis.
- Permitir filtros por janela, temporada, posição, idade e clube.
- Identificar explicitamente estimativas e valores sem confirmação documental.
- Salários e contratos só podem ser exibidos quando houver fonte legítima, cobertura e condições de uso adequadas.

**Ponto de integração sugerido:** módulo de clubes, catálogo de jogadores e dados de transferências. Salários e orçamento ficam condicionados à existência de dados confiáveis.

### 3. Análise tática de partida ao vivo

**O que a referência demonstra**
- Campo com formações e relações entre jogadores.
- Camadas de calor e setas de movimentação/passe.
- Indicadores coletivos na base do painel.
- Assistente lateral com perguntas em linguagem natural.
- Recomendações táticas ligadas a espaços e comportamentos observados.

**Aplicação no Tactical Intelligence Lab**
- Exibir estado da partida, minuto, placar e escalações com atualização controlada.
- Separar rede de passes, mapa de eventos, posicionamento médio e tracking: cada visualização exige um tipo de dado diferente.
- Associar cada insight a evidências concretas, por exemplo eventos, sequência temporal, zona e amostra utilizada.
- Permitir que o usuário abra a evidência que originou uma recomendação.
- Evitar frases determinísticas. O assistente deve indicar hipótese, grau de confiança e limitações da fonte.

**Ponto de integração sugerido:** centro da partida, redes de passe e assistente. Recursos ao vivo não devem atrasar consultas históricas nem bloquear a interface.

### 4. Dossiê individual do jogador

**O que a referência demonstra**
- Identificação do atleta, clube, posição e dados biográficos.
- Indicadores comparados com outros atletas da mesma função.
- Histórico de valor de mercado.
- Recorte por temporada/competição.
- Visualização específica de ações da posição, como finalizações e defesas para goleiros.

**Aplicação no Tactical Intelligence Lab**
- Organizar o perfil em blocos: identidade, desempenho, função, evolução, mercado e evidências.
- Dar prioridade a minutos, partidas, métricas por 90 minutos e amostra.
- Permitir alternar temporada, competição e clube sem misturar contextos.
- Exibir gráficos específicos de posição; métricas de goleiro não devem compartilhar a mesma régua de jogadores de linha.
- Mostrar o histórico de valor com data e fonte, sem preencher lacunas por interpolação silenciosa.

**Ponto de integração sugerido:** perfil de jogador e busca de atletas.

### 5. Comparação por percentis e perfil funcional

**O que a referência demonstra**
- Cartão de identificação e posição principal no campo.
- Gráficos radiais por grupos de atributos.
- Pontos fortes destacados.
- Comparação interativa entre atletas da mesma posição.
- Alternância entre valores absolutos, percentis e cores.

**Aplicação no Tactical Intelligence Lab**
- Permitir comparação de dois ou mais atletas, respeitando a função efetivamente desempenhada.
- Definir explicitamente a população de referência: liga, temporada, posição/função e corte mínimo de minutos.
- Distinguir percentil, valor absoluto e métrica por 90 minutos.
- Inverter corretamente indicadores negativos (por exemplo, perdas de posse), sem pintar um valor alto como algo positivo.
- Informar tamanho da amostra e cobertura de cada atributo.
- Não calcular percentil de atributo ausente nem tratar ausência como desempenho ruim.
- Permitir que o usuário ajuste dimensões e pesos sem esconder a configuração padrão usada no ranking.

**Ponto de integração sugerido:** comparação de jogadores, Scout e avaliação individual.

## Ordem recomendada de execução

| Ordem | Entrega | Prioridade | Dependências e condição de entrada |
|---|---|---|---|
| 1 | Auditoria das telas e componentes existentes | P0 | Inventário de páginas, testes de regressão e medição de latência |
| 2 | Melhorias incrementais no perfil individual e comparação | P1 | Identidades consistentes, métricas normalizadas, amostras e proveniência |
| 3 | Painel de equipe e partida com indicadores verificáveis | P1 | Estatísticas por equipe, escalações e dados de eventos disponíveis |
| 4 | Mapas de calor, redes e visualizações espaciais avançadas | P1/P2 | Coordenadas/eventos compatíveis; tracking somente quando houver fonte |
| 5 | Inteligência de transferências e histórico de valores | P2 | Entidades reconciliadas, moedas, datas e fonte por registro |
| 6 | Visão financeira de elenco e salários | P2 | Dados legais e confiáveis de salários/contratos; sem estimativas apresentadas como fatos |
| 7 | Assistente tático contextual dentro dos painéis | P1/P2 | Recuperação de evidências, guarda de fatos, testes de resposta e medição de tempo |

A ordem é deliberada: a referência visual não justifica implementar telas antes de confirmar que os dados necessários existem e são confiáveis.

## Critérios de aceitação para qualquer nova tela

- Nenhuma funcionalidade anterior é removida ou tem seu comportamento alterado sem teste e justificativa.
- A tela funciona com dados completos, parciais e indisponíveis.
- Cada número apresentado pode ser rastreado até uma fonte ou fórmula documentada.
- O filtro selecionado aparece claramente e não mistura temporadas/competições sem aviso.
- Gráficos não confundem valores absolutos, por 90 minutos, percentis e previsões.
- Estados vazios, carregamento e falha de fonte são tratados sem travar o restante do aplicativo.
- Testes de regressão relevantes passam antes da publicação.
- A latência é comparada com a versão anterior usando o mesmo banco e cenário.
- Uma mudança de interface não dispara sincronização ou treinamento pesado automaticamente.

## Relação com o Plano Diretor

Este documento complementa `docs/PLANO_DIRETOR.md`. O Plano Diretor continua sendo a referência de arquitetura, dados, modelos, governança e publicação. Este arquivo detalha como as cinco referências visuais podem orientar a evolução da interface sem transformar mockups em funcionalidades supostamente existentes.

## Nota sobre os arquivos de referência

As cinco imagens foram inspecionadas e descritas neste documento, mas os arquivos binários originais não foram adicionados a esta alteração do repositório. Assim, este commit registra seus requisitos e decisões de produto sem substituir nem alterar imagens ou código da aplicação.
