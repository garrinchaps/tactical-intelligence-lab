# Brasileirão: o que cada fonte entrega

Nenhuma fonte aberta publica **lances com coordenadas** do futebol brasileiro (StatsBomb, Wyscout e OpenPlay
não cobrem o Brasil). Por isso os jogos do Brasileirão entram no nível **ESTATÍSTICAS** e o app junta, para a
mesma partida, o que cada fonte tem (mesma data ±1 dia e mesmos times; divergências ficam registradas, nunca
viram média).

| fonte | temporadas | o que traz | como carregar |
|---|---|---|---|
| Brasileirão Dataset (adaoduque) | 2003–2023 (estatísticas 2015–2023) | chutes, no alvo, posse, passes, precisão de passe, faltas, cartões, impedimentos, escanteios; gols e cartões por minuto | `--only brasileirao` (automático, todo dia) |
| ESPN | 2018–hoje | posse, chutes, passes e precisão, cruzamentos, bolas longas, desarmes, interceptações, cortes, defesas; escalações e números por jogador | `--only espn_historico --desde 2018` |
| API-Football (chave grátis) | as temporadas que o plano da chave liberar | **xG**, passes, posse, finalizações por zona, escalações com formação, nota e números de cada jogador | `--only estatisticas_brasil` (e todo dia, dentro da cota) |
| Súmulas da CBF (BrazilianFootball) | 2013–2025, Séries A–D e Copa do Brasil | placar, estádio, gols e cartões por minuto | `--only cbf` |

**xG do Brasileirão** só existe na API-Football. O comando `estatisticas_brasil` busca 20 jogos completos por
requisição (uma temporada inteira da Série A em ~20 requisições), pula os que já têm estatística e para na cota
do dia, deixando 15 requisições livres para o app. Temporadas que o plano da chave não cobre aparecem como
"o plano da chave não cobre" e são puladas sem gastar cota de novo.
