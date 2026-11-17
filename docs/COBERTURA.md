# Cobertura da base — Tactical Intelligence Lab

Gerado em 17/11/2026 19:56 a partir de `tactical_lab.db` · **437.347 partidas reais** (simulações e uploads fora da conta).


> Honestidade técnica: estes números saem direto do banco. Ligas e temporadas que não aparecem aqui **não estão em nenhuma fonte aberta sincronizada** — são lacunas reais, não zeros estimados.

## Níveis de dado

- **EVENTOS** — lances com coordenadas (passes, chutes, duelos): análise espacial completa.
- **ESTATÍSTICAS** — estatísticas de equipe (chutes, no alvo, posse, escanteios, faltas, cartões).
- **SÓ PLACAR** — placar e, quando a fonte traz, autores dos gols e escalações. Sem estatísticas.

## Visão geral

| nível | partidas | % |
|---|---|---|
| ESTATÍSTICAS | 94598 | 22% |
| EVENTOS | 32449 | 7% |
| SÓ PLACAR | 310300 | 71% |

## Inconsistências detectadas

Nenhuma.

## Por fonte

| fonte | ESTATÍSTICAS | EVENTOS | SÓ PLACAR | total |
|---|---|---|---|---|
| fdcouk | 59227 | 0 | 67066 | 126293 |
| fotmob | 28486 | 0 | 75310 | 103796 |
| openfootball | 0 | 0 | 89781 | 89781 |
| intl | 0 | 0 | 49923 | 49923 |
| openplay | 0 | 26547 | 0 | 26547 |
| espn | 1591 | 0 | 21552 | 23143 |
| brasileirao | 3410 | 0 | 5375 | 8785 |
| statsbomb | 0 | 3961 | 0 | 3961 |
| open_matchday | 1812 | 0 | 1293 | 3105 |
| wyscout | 0 | 1941 | 0 | 1941 |
| api_football | 72 | 0 | 0 | 72 |

## Preenchimento de campos

| campo | preenchido | base |
|---|---|---|
| data | 100% | todas as partidas |
| país | 65% | todas as partidas |
| rodada | 24% | todas as partidas |
| estádio | 20% | todas as partidas |
| árbitro | 5% | todas as partidas |
| linha do tempo (gols/cartões) | 12% | todas as partidas |
| escalações | 7% | todas as partidas |
| estatística: chutes | 99% | 94598 partidas com estatísticas |
| estatística: no alvo | 97% | 94598 partidas com estatísticas |
| estatística: posse | 35% | 94598 partidas com estatísticas |
| estatística: escanteios | 99% | 94598 partidas com estatísticas |
| estatística: faltas | 97% | 94598 partidas com estatísticas |
| estatística: amarelos | 100% | 94598 partidas com estatísticas |
| estatística: xG | 25% | 94598 partidas com estatísticas |
| eventos já baixados | 17% | 32449 partidas com eventos na fonte |

## Por competição e temporada (maiores 400)

`estatísticas ausentes` lista, para os jogos com estatísticas, quais indicadores nenhuma partida daquela temporada traz (`n/a` = não há jogos com estatísticas).


| competição | temporada | partidas | EVENTOS | eventos em disco | ESTATÍSTICAS | SÓ PLACAR | fontes | estatísticas ausentes |
|---|---|---|---|---|---|---|---|---|
| La Liga | 2017/2018 | 1175 | 796 | 0 | 379 | 0 | fdcouk, openplay, statsbomb, wyscout | posse, xG |
| Ligue 1 | 2017/2018 | 1140 | 760 | 0 | 380 | 0 | fdcouk, openplay, wyscout | posse, xG |
| Serie A | 2017/2018 | 1140 | 760 | 0 | 380 | 0 | fdcouk, openplay, wyscout | posse, xG |
| Premier League | 2017/2018 | 1139 | 760 | 0 | 379 | 0 | fdcouk, openplay, wyscout | posse, xG |
| MLS | 2025 | 1081 | 0 | 0 | 0 | 1081 | espn, fotmob | n/a |
| MLS | 2026 | 1021 | 0 | 0 | 15 | 1006 | espn, fotmob | — |
| Campeonato Brasileiro Série A | 2021 | 872 | 0 | 0 | 492 | 380 | brasileirao, fdcouk | xG |
| La Liga | 2020/2021 | 795 | 415 | 11 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| La Liga | 2018/2019 | 794 | 414 | 1 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| La Liga | 2016/2017 | 794 | 414 | 0 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| La Liga | 2019/2020 | 792 | 413 | 0 | 379 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| Ligue 1 | 2022/2023 | 790 | 411 | 0 | 379 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| Ligue 1 | 2021/2022 | 781 | 401 | 0 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| Serie A | 2023/2024 | 760 | 380 | 145 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2016/2017 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2018/2019 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2015/2016 | 760 | 760 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| Serie A | 2020/2021 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2025/2026 | 760 | 380 | 380 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2023/2024 | 760 | 380 | 142 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2022/2023 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2024/2025 | 760 | 380 | 380 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2018/2019 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2019/2020 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2024 | 760 | 0 | 0 | 1 | 759 | brasileirao, fdcouk | posse, xG |
| Ligue 1 | 2020/2021 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2015/2016 | 760 | 760 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| Campeonato Brasileiro Série A | 2018 | 760 | 0 | 0 | 380 | 380 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2017 | 760 | 0 | 0 | 379 | 381 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2013 | 760 | 0 | 0 | 0 | 760 | brasileirao, fdcouk | n/a |
| Campeonato Brasileiro Série A | 2022 | 760 | 0 | 0 | 380 | 380 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2014 | 760 | 0 | 0 | 17 | 743 | brasileirao, fdcouk | xG |
| Brasileirão Série B | 2026 | 760 | 0 | 0 | 760 | 0 | espn, fotmob | — |
| Brasileirão Série B | 2025 | 760 | 0 | 0 | 760 | 0 | espn, fotmob | — |
| Brasileirão Série A | 2025 | 760 | 0 | 0 | 760 | 0 | espn, fotmob | — |
| Premier League | 2020/2021 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2015/2016 | 760 | 760 | 2 | 0 | 0 | openplay, statsbomb | n/a |
| Premier League | 2024/2025 | 760 | 380 | 380 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2022/2023 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2025/2026 | 760 | 380 | 380 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2016/2017 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2019 | 759 | 0 | 0 | 358 | 401 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2012 | 759 | 0 | 0 | 1 | 758 | brasileirao, fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2015 | 759 | 0 | 0 | 382 | 377 | brasileirao, fdcouk | xG |
| Ligue 1 | 2016/2017 | 759 | 379 | 0 | 379 | 1 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2023 | 759 | 0 | 0 | 380 | 379 | brasileirao, fdcouk | xG |
| Ligue 1 | 2018/2019 | 759 | 380 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2023/2024 | 759 | 380 | 145 | 379 | 0 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2016 | 758 | 0 | 0 | 379 | 379 | brasileirao, fdcouk | xG |
| La Liga | 2025/2026 | 758 | 380 | 380 | 378 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2021/2022 | 758 | 379 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2019/2020 | 758 | 379 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2024/2025 | 758 | 380 | 379 | 378 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2021/2022 | 757 | 377 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2015/2016 | 757 | 757 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| Serie A | 2022/2023 | 755 | 375 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2021/2022 | 754 | 374 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Argentina — Primera Nacional | 2024 | 745 | 0 | 0 | 0 | 745 | fotmob | n/a |
| Major League Soccer | 2025 | 704 | 0 | 0 | 0 | 704 | fdcouk, openfootball | n/a |
| Campeonato Brasileiro Série A | 2026 | 682 | 0 | 0 | 0 | 682 | fdcouk, open_matchday | n/a |
| Brasileirão Série A | 2026 | 682 | 0 | 0 | 682 | 0 | espn, fotmob | — |
| Argentina — Primera Nacional | 2022 | 680 | 0 | 0 | 0 | 680 | fotmob | n/a |
| Argentina — Primera Nacional | 2023 | 669 | 0 | 0 | 0 | 669 | fotmob | n/a |
| Argentina — Primera Nacional | 2026 | 655 | 0 | 0 | 0 | 655 | fotmob | n/a |
| Campeonato Brasileiro Série A | 2020 | 648 | 0 | 0 | 267 | 381 | brasileirao, fdcouk | xG |
| Argentina — Primera Nacional | 2025 | 634 | 0 | 0 | 0 | 634 | fotmob | n/a |
| Ligue 1 | 2024/2025 | 612 | 306 | 306 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2025/2026 | 612 | 306 | 306 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2017/2018 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2016/2017 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2019/2020 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2018/2019 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2023/2024 | 611 | 305 | 117 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2020/2021 | 611 | 306 | 0 | 305 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2025/2026 | 611 | 306 | 306 | 305 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2023/2024 | 611 | 306 | 117 | 305 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2024/2025 | 611 | 306 | 306 | 304 | 1 | fdcouk, openplay | posse, xG |
| Bundesliga | 2021/2022 | 611 | 306 | 0 | 305 | 0 | fdcouk, openplay | posse, xG |
| Brasileirão Série D | 2026 | 610 | 0 | 0 | 0 | 610 | fotmob | n/a |
| Bundesliga | 2022/2023 | 610 | 304 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| FIFA World Cup qualification | 2021 | 609 | 0 | 0 | 0 | 609 | intl | n/a |
| Argentina — Primera Nacional | 2021 | 590 | 0 | 0 | 0 | 590 | fotmob | n/a |
| Ligue 1 | 2019/2020 | 558 | 279 | 0 | 279 | 0 | fdcouk, openplay | posse, xG |
| Championship | 2021-2022 | 557 | 0 | 0 | 557 | 0 | fotmob | — |
| Championship | 2022-2023 | 557 | 0 | 0 | 557 | 0 | fotmob | — |
| Championship | 2025 | 557 | 0 | 0 | 0 | 557 | espn | n/a |
| English Championship | 2021/22 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| English Championship | 2024/25 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| Championship | 2024-2025 | 557 | 0 | 0 | 556 | 1 | fotmob | — |
| English Championship | 2025/26 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| English Championship | 2022/23 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| Championship | 2023-2024 | 557 | 0 | 0 | 557 | 0 | fotmob | — |
| English Championship | 2023/24 | 556 | 0 | 0 | 0 | 556 | openfootball | n/a |
| Championship | 2025-2026 | 555 | 0 | 0 | 555 | 0 | fotmob | — |
| Championship | 2016/2017 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2024/2025 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2019/2020 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| League Two | 2024/2025 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| League One | 2024/2025 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2004 | 552 | 0 | 0 | 0 | 552 | brasileirao | n/a |
| Campeonato Brasileiro Série A | 2003 | 552 | 0 | 0 | 0 | 552 | brasileirao | n/a |
| English Championship | 2012/13 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2020/21 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| National League | 2025/2026 | 552 | 0 | 0 | 552 | 0 | fdcouk | chutes, no alvo, posse, escanteios, faltas, xG |
| English League One | 2012/13 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2011/12 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2013/14 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2011/12 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2013/14 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2014/15 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| Championship | 2023/2024 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2021/2022 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2022/2023 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2017/2018 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| English League One | 2024/25 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2013/14 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2015/16 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2019/20 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2020/21 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2015/16 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2018/19 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2020/21 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2018/19 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| League One | 2025/2026 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| League Two | 2025/2026 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| English Championship | 2010/11 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English Championship | 2011/12 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League One | 2010/11 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| National League | 2024/2025 | 551 | 0 | 0 | 551 | 0 | fdcouk | chutes, no alvo, posse, escanteios, faltas, xG |
| English League One | 2014/15 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English Championship | 2018/19 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| Championship | 2018/2019 | 551 | 0 | 0 | 550 | 1 | fdcouk | posse, xG |
| English Championship | 2014/15 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League Two | 2012/13 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League Two | 2024/25 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| Championship | 2025/2026 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| Championship | 2020/2021 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| English League Two | 2015/16 | 550 | 0 | 0 | 0 | 550 | openfootball | n/a |
| English League Two | 2010/11 | 549 | 0 | 0 | 0 | 549 | openfootball | n/a |
| Major League Soccer | 2023 | 527 | 6 | 0 | 0 | 521 | fdcouk, statsbomb | n/a |
| Major League Soccer | 2024 | 522 | 0 | 0 | 0 | 522 | fdcouk | n/a |
| MLS | 2024 | 522 | 0 | 0 | 0 | 522 | fotmob | n/a |
| MLS | 2023 | 521 | 0 | 0 | 0 | 521 | fotmob | n/a |
| J1 League | 2025 | 516 | 0 | 0 | 0 | 516 | espn, openfootball | n/a |
| Liga Profesional | 2025 | 510 | 0 | 0 | 0 | 510 | fdcouk | n/a |
| Major League Soccer | 2026 | 510 | 0 | 0 | 1 | 509 | fdcouk | posse, xG |
| Brasileirão Série D | 2025 | 510 | 0 | 0 | 0 | 510 | fotmob | n/a |
| Liga Profesional (ARG) | 2025 | 510 | 0 | 0 | 0 | 510 | espn | n/a |
| Bundesliga | 2025/26 | 501 | 0 | 0 | 0 | 501 | openfootball | n/a |
| Liga Profesional (ARG) | 2026 | 495 | 0 | 0 | 0 | 495 | espn | n/a |
| Liga Profesional | 2026 | 494 | 0 | 0 | 1 | 493 | fdcouk | posse, xG |
| FIFA World Cup qualification | 2025 | 492 | 0 | 0 | 0 | 492 | intl | n/a |
| FIFA World Cup qualification | 2001 | 491 | 0 | 0 | 0 | 491 | intl | n/a |
| MLS | 2022 | 489 | 0 | 0 | 0 | 489 | fotmob | n/a |
| Major League Soccer | 2022 | 489 | 0 | 0 | 0 | 489 | fdcouk | n/a |
| Italian Serie B | 2014/15 | 472 | 0 | 0 | 0 | 472 | openfootball | n/a |
| MLS | 2021 | 472 | 0 | 0 | 0 | 472 | fotmob | n/a |
| Italian Serie B | 2017/18 | 472 | 0 | 0 | 0 | 472 | openfootball | n/a |
| Italian Serie B | 2015/16 | 472 | 0 | 0 | 0 | 472 | openfootball | n/a |
| Italian Serie B | 2013/14 | 471 | 0 | 0 | 0 | 471 | openfootball | n/a |
| Major League Soccer | 2021 | 471 | 0 | 0 | 0 | 471 | fdcouk | n/a |
| Italian Serie B | 2016/17 | 469 | 0 | 0 | 0 | 469 | openfootball | n/a |
| La Liga 2 | 2023-2024 | 468 | 0 | 0 | 468 | 0 | fotmob | xG |
| La Liga 2 | 2025 | 468 | 0 | 0 | 0 | 468 | espn | n/a |
| La Liga 2 | 2021-2022 | 468 | 0 | 0 | 0 | 468 | fotmob | n/a |
| La Liga 2 | 2025-2026 | 468 | 0 | 0 | 468 | 0 | fotmob | — |
| Liga Profesional  (Argentina) | 2015 | 468 | 0 | 0 | 1 | 467 | fdcouk | posse, xG |
| La Liga 2 | 2022-2023 | 468 | 0 | 0 | 180 | 288 | fotmob | — |
| La Liga 2 | 2024-2025 | 468 | 0 | 0 | 468 | 0 | fotmob | — |
| La Liga 2 | 2022/2023 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2021/2022 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| Serie B | 2017/2018 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2019/2020 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2024/2025 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2025/2026 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2005 | 462 | 0 | 0 | 0 | 462 | brasileirao | n/a |
| La Liga 2 | 2018/2019 | 462 | 0 | 0 | 441 | 21 | fdcouk | posse, xG |
| Segunda División de España | 2017/18 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| La Liga 2 | 2017/2018 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| Segunda División de España | 2019/20 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2020/21 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| La Liga 2 | 2016/2017 | 462 | 0 | 0 | 0 | 462 | fdcouk | n/a |
| Segunda División de España | 2012/13 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2015/16 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2014/15 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2016/17 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2018/19 | 461 | 0 | 0 | 0 | 461 | openfootball | n/a |
| Segunda División de España | 2013/14 | 461 | 0 | 0 | 0 | 461 | openfootball | n/a |
| La Liga 2 | 2020/2021 | 461 | 0 | 0 | 461 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2023/2024 | 461 | 0 | 0 | 461 | 0 | fdcouk | posse, xG |
| Serie B | 2016/2017 | 461 | 0 | 0 | 0 | 461 | fdcouk | n/a |
| Spain Segunda División | 2024/25 | 452 | 0 | 0 | 0 | 452 | openfootball | n/a |
| Colômbia | 2025 | 451 | 0 | 0 | 0 | 451 | espn | n/a |
| Liga Profesional  (Argentina) | 2016/2017 | 450 | 0 | 0 | 0 | 450 | fdcouk | n/a |
| English League Two | 2019/20 | 440 | 0 | 0 | 0 | 440 | openfootball | n/a |
| Brasileirão Série C | 2025 | 432 | 0 | 0 | 0 | 432 | espn, fotmob | n/a |
| Friendly | 2010 | 422 | 0 | 0 | 0 | 422 | intl | n/a |
| Major League Soccer | 2019 | 421 | 0 | 0 | 0 | 421 | fdcouk | n/a |
| Turkish Süper Lig | 2020/21 | 420 | 0 | 0 | 0 | 420 | openfootball | n/a |
| Friendly | 2018 | 420 | 0 | 0 | 0 | 420 | intl | n/a |
| Süper Lig | 2020/2021 | 420 | 0 | 0 | 420 | 0 | fdcouk | posse, xG |
| La Liga | 2014/2015 | 418 | 418 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| FIFA World Cup qualification | 2008 | 414 | 0 | 0 | 0 | 414 | intl | n/a |
| FIFA World Cup qualification | 1997 | 410 | 0 | 0 | 0 | 410 | intl | n/a |
| FIFA World Cup qualification | 2004 | 408 | 0 | 0 | 0 | 408 | intl | n/a |
| Major League Soccer | 2018 | 408 | 0 | 0 | 0 | 408 | fdcouk | n/a |
| Friendly | 2008 | 407 | 0 | 0 | 0 | 407 | intl | n/a |
| Friendly | 2012 | 406 | 0 | 0 | 0 | 406 | intl | n/a |
| English League One | 2019/20 | 398 | 0 | 0 | 0 | 398 | openfootball | n/a |
| Colômbia | 2026 | 394 | 0 | 0 | 10 | 384 | espn | xG |
| Italian Serie B | 2019/20 | 390 | 0 | 0 | 0 | 390 | openfootball | n/a |
| Serie B | 2023-2024 | 390 | 0 | 0 | 0 | 390 | fotmob | n/a |
| Serie B (ITA) | 2025 | 390 | 0 | 0 | 0 | 390 | espn | n/a |
| Serie B | 2021-2022 | 390 | 0 | 0 | 0 | 390 | fotmob | n/a |
| Major League Soccer | 2017 | 390 | 0 | 0 | 0 | 390 | fdcouk | n/a |
| Serie B | 2025-2026 | 390 | 0 | 0 | 0 | 390 | fotmob | n/a |
| Serie B | 2022-2023 | 390 | 0 | 0 | 0 | 390 | fotmob | n/a |
| Serie B | 2024-2025 | 389 | 0 | 0 | 0 | 389 | fotmob | n/a |
| Italian Serie B | 2020/21 | 388 | 0 | 0 | 0 | 388 | openfootball | n/a |
| Italian Serie B | 2024/25 | 387 | 0 | 0 | 0 | 387 | openfootball | n/a |
| Turquia — 1. Lig | 2025-2026 | 385 | 0 | 0 | 0 | 385 | fotmob | n/a |
| Turquia — 1. Lig | 2024-2025 | 385 | 0 | 0 | 0 | 385 | fotmob | n/a |
| Friendly | 2014 | 384 | 0 | 0 | 0 | 384 | intl | n/a |
| Liga Profesional  (Argentina) | 2013/2014 | 382 | 0 | 0 | 0 | 382 | fdcouk | n/a |
| Liga Profesional  (Argentina) | 2012/2013 | 381 | 0 | 0 | 0 | 381 | fdcouk | n/a |
| Serie A | 2022-2023 | 381 | 0 | 0 | 381 | 0 | fotmob | — |
| Primera División de España | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileirão Série B | 2021 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Eerste Divisie | 2025-2026 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Eerste Divisie | 2022-2023 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Eerste Divisie | 2021-2022 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Serie B | 2025/2026 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Spain Primera División | 2025/26 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileiro Série A | 2025 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2025/26 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Premier League | 2025/26 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileirão Série B | 2023 | 380 | 0 | 0 | 380 | 0 | fotmob | xG |
| French Ligue 1 | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileirão Série B | 2022 | 380 | 0 | 0 | 379 | 1 | fotmob | xG |
| French Ligue 1 | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Serie B | 2022/2023 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| French Ligue 2 | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Serie A | 2014/2015 | 380 | 380 | 0 | 0 | 0 | openplay | n/a |
| Serie B | 2023/2024 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Brasileirão Série A | 2021 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Brasileirão Série A | 2022 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Primera División de España | 2023/24 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| La Liga | 2021-2022 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Serie B | 2020/2021 | 380 | 0 | 0 | 379 | 1 | fdcouk | posse, xG |
| English Premier League | 2024/25 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2013/14 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileirão Série B | 2024 | 380 | 0 | 0 | 380 | 0 | fotmob | xG |
| French Ligue 1 | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2023/24 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2021/22 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| La Liga | 2025 | 380 | 0 | 0 | 0 | 380 | espn | n/a |
| Primera División de España | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| La Liga | 2024-2025 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| English Premier League | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| La Liga | 2025-2026 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| La Liga | 2023-2024 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Serie B | 2021/2022 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| La Liga | 2022-2023 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| French Ligue 1 | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2010/11 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Serie A | 2023-2024 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Serie A | 2021-2022 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| English Premier League | 2011/12 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2012/13 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2013/14 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2019/20 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2021/22 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Eerste Divisie | 2023-2024 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Serie A | 2025 | 380 | 0 | 0 | 0 | 380 | espn | n/a |
| Serie A | 2024-2025 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Serie A | 2025-2026 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Brasileirão Série A | 2024 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Campeonato Brasileiro Série A | 2008 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Campeonato Brasileiro Série A | 2009 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Campeonato Brasileiro Série B | 2026 | 380 | 0 | 0 | 0 | 380 | open_matchday | n/a |
| Campeonato Brasileiro Série A | 2007 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Eerste Divisie | 2024-2025 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Ligue 2 | 2021-2022 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Deutsche 3. Liga | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| J1 League (Japan) | 2025 | 380 | 0 | 0 | 1 | 379 | fdcouk | posse, xG |
| Brasileirão Série A | 2023 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| J1 League (Japan) | 2024 | 380 | 0 | 0 | 0 | 380 | fdcouk | n/a |
| Süper Lig | 2023-2024 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Brasileiro Série A | 2019 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileiro Série A | 2020 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2021/22 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2019/20 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2023/24 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Süper Lig | 2021-2022 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Italian Serie A | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2013/14 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Premier League | 2025 | 380 | 0 | 0 | 0 | 380 | espn | n/a |
| Premier League | 2025-2026 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Premier League | 2014/2015 | 380 | 380 | 0 | 0 | 0 | openplay | n/a |
| Premier League | 2024-2025 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Premier League | 2021-2022 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Premier League | 2022-2023 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Premier League | 2023-2024 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Serie B | 2024/2025 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2010 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Campeonato Brasileiro Série A | 2011 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Campeonato Brasileiro Série A | 2025 | 380 | 0 | 0 | 0 | 380 | fdcouk | n/a |
| J1 League (Japan) | 2021 | 380 | 0 | 0 | 0 | 380 | fdcouk | n/a |
| Deutsche 3. Liga | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2019/20 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Ligue 2 | 2022/2023 | 380 | 0 | 0 | 379 | 1 | fdcouk | posse, xG |
| Ligue 2 | 2022-2023 | 380 | 0 | 0 | 0 | 380 | fotmob | n/a |
| Ligue 1 | 2021-2022 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Ligue 1 | 2014/2015 | 380 | 380 | 0 | 0 | 0 | openplay | n/a |
| Ligue 1 | 2022-2023 | 380 | 0 | 0 | 380 | 0 | fotmob | — |
| Ligue 2 | 2017/2018 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, faltas, xG |
| Ligue 2 | 2020/2021 | 380 | 0 | 0 | 379 | 1 | fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2006 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| French Ligue 1 | 2016/17 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| French Ligue 1 | 2014/15 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| French Ligue 2 | 2018/19 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Primera División de España | 2012/13 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Serie B | 2019/2020 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| English Premier League | 2019/20 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Primera División de España | 2021/22 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Primera División de España | 2018/19 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Süper Lig | 2023/2024 | 379 | 0 | 0 | 378 | 1 | fdcouk | posse, xG |
| Italian Serie A | 2017/18 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Italian Serie A | 2020/21 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Süper Lig | 2021/2022 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Ligue 2 | 2018/2019 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Ligue 2 | 2023-2024 | 379 | 0 | 0 | 0 | 379 | fotmob | n/a |
| Ligue 2 | 2023/2024 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Ligue 2 | 2021/2022 | 379 | 0 | 0 | 378 | 1 | fdcouk | posse, xG |
| Deutsche 3. Liga | 2015/16 | 378 | 0 | 0 | 0 | 378 | openfootball | n/a |
| Ligue 2 | 2016/2017 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| English Premier League | 2016/17 | 378 | 0 | 0 | 0 | 378 | openfootball | n/a |
| Liga Profesional | 2017/2018 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| Liga Profesional | 2023 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| Argentina — Liga Profesional | 2024 | 378 | 0 | 0 | 378 | 0 | fotmob | — |
| Argentina — Liga Profesional | 2023 | 378 | 0 | 0 | 378 | 0 | fotmob | — |
| Liga Profesional | 2022 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| Liga Profesional | 2024 | 377 | 0 | 0 | 0 | 377 | fdcouk | n/a |
| Friendly | 2011 | 374 | 0 | 0 | 0 | 374 | intl | n/a |
| Friendly | 2004 | 372 | 0 | 0 | 0 | 372 | intl | n/a |
| Italian Serie A | 2024/25 | 370 | 0 | 0 | 0 | 370 | openfootball | n/a |
| Spain Primera División | 2024/25 | 370 | 0 | 0 | 0 | 370 | openfootball | n/a |
| Friendly | 2000 | 362 | 0 | 0 | 0 | 362 | intl | n/a |
| Coupe de France | 2025-2026 | 361 | 0 | 0 | 0 | 361 | fotmob | n/a |
| Championship | 2026/2027 | 359 | 0 | 0 | 359 | 0 | fdcouk, open_matchday | posse, xG |
| Coupe de France | 2024-2025 | 358 | 0 | 0 | 0 | 358 | fotmob | n/a |
| Coupe de France | 2023-2024 | 358 | 0 | 0 | 0 | 358 | fotmob | n/a |
| Major League Soccer | 2016 | 357 | 0 | 0 | 0 | 357 | fdcouk | n/a |
| Major League Soccer | 2015 | 357 | 0 | 0 | 0 | 357 | fdcouk | n/a |
| English League One | 2025/26 | 356 | 0 | 0 | 0 | 356 | openfootball | n/a |
| Italian Serie B | 2018/19 | 352 | 0 | 0 | 0 | 352 | openfootball | n/a |
| FIFA World Cup qualification | 2005 | 351 | 0 | 0 | 0 | 351 | intl | n/a |
| League Two | 2026/2027 | 348 | 0 | 0 | 348 | 0 | fdcouk, open_matchday | posse, xG |
| Friendly | 2006 | 348 | 0 | 0 | 0 | 348 | intl | n/a |
| FIFA World Cup qualification | 2013 | 347 | 0 | 0 | 0 | 347 | intl | n/a |
| Friendly | 2002 | 347 | 0 | 0 | 0 | 347 | intl | n/a |
| Turquia — 1. Lig | 2022-2023 | 347 | 0 | 0 | 0 | 347 | fotmob | n/a |
| Turquia — 1. Lig | 2021-2022 | 347 | 0 | 0 | 0 | 347 | fotmob | n/a |
| Peru — Liga 1 | 2022 | 346 | 0 | 0 | 0 | 346 | fotmob | n/a |
| Peru — Liga 1 | 2023 | 344 | 0 | 0 | 0 | 344 | fotmob | n/a |
| Friendly | 2022 | 343 | 0 | 0 | 0 | 343 | intl | n/a |
| Süper Lig | 2024/2025 | 342 | 0 | 0 | 341 | 1 | fdcouk | posse, xG |
| Süper Lig | 2024-2025 | 342 | 0 | 0 | 0 | 342 | fotmob | n/a |
| Serie B | 2018/2019 | 342 | 0 | 0 | 341 | 1 | fdcouk | posse, xG |
| Liga MX | 2021/2022 | 342 | 0 | 0 | 0 | 342 | fdcouk | n/a |
| Liga MX | 2020/2021 | 342 | 0 | 0 | 0 | 342 | fdcouk | n/a |
| Süper Lig | 2022-2023 | 342 | 0 | 0 | 0 | 342 | fotmob | n/a |
| Liga MX | 2022/2023 | 342 | 0 | 0 | 0 | 342 | fdcouk | n/a |
| Liga MX | 2020/21 | 341 | 0 | 0 | 0 | 341 | openfootball | n/a |
| Süper Lig | 2022/2023 | 341 | 0 | 0 | 313 | 28 | fdcouk | posse, xG |
| Liga MX | 2023/2024 | 340 | 0 | 0 | 0 | 340 | fdcouk | n/a |
| Coupe de France | 2021-2022 | 340 | 0 | 0 | 0 | 340 | fotmob | n/a |
| Liga MX | 2024/25 | 340 | 0 | 0 | 0 | 340 | openfootball | n/a |
| J1 League | 2026 | 340 | 0 | 0 | 0 | 340 | espn | n/a |

## Qualidade dos dados

- Partidas auditadas: 437347
- Bloqueadas pela validação (placar negativo, equipe vazia, data impossível): 0
- Avisos de data fora da temporada: 499
- Duplicatas reais (mesmo conteúdo SHA-256, mesma fonte, ids diferentes): 0
- Mesma partida presente em outra fonte (ligações esperadas): 95646
- Lances com minuto fora de 0–130: 0 · eventos fora do campo/minuto: 12


Primeiros avisos:


| match_id | fonte | aviso |
|---|---|---|
| 12005729447 | fotmob | data 2026-08-12 fora da temporada 2025-2026 |
| 11001980554 | openplay | data 2026-08-12 fora da temporada 2025/2026 |
| 500723734 | espn | data 2026-03-31 fora da temporada 2024 |
| 500723732 | espn | data 2026-03-31 fora da temporada 2024 |
| 500723733 | espn | data 2026-03-26 fora da temporada 2024 |
| 500723731 | espn | data 2026-03-26 fora da temporada 2024 |
| 500684667 | espn | data 2025-09-09 fora da temporada 2023 |
| 500684666 | espn | data 2025-09-09 fora da temporada 2023 |
| 500684665 | espn | data 2025-09-09 fora da temporada 2023 |
| 500684664 | espn | data 2025-09-09 fora da temporada 2023 |
| 500684663 | espn | data 2025-09-09 fora da temporada 2023 |
| 500684659 | espn | data 2025-09-05 fora da temporada 2023 |
| 500684662 | espn | data 2025-09-04 fora da temporada 2023 |
| 500684661 | espn | data 2025-09-04 fora da temporada 2023 |
| 500684660 | espn | data 2025-09-04 fora da temporada 2023 |
| 500684658 | espn | data 2025-09-04 fora da temporada 2023 |
| 12004798405 | fotmob | data 2025-08-13 fora da temporada 2024-2025 |
| 11001900643 | openplay | data 2025-08-13 fora da temporada 2024/2025 |
| 500684656 | espn | data 2025-06-11 fora da temporada 2023 |
| 500684655 | espn | data 2025-06-11 fora da temporada 2023 |

## Últimas sincronizações

| fonte | última | ok | erros |
|---|---|---|---|
| api_football | 2026-11-17 22:51:01 | 14 | 0 |
| brasileirao | 2026-11-17 04:38:16 | 3 | 0 |
| cbf | 2026-11-15 18:49:15 | 3 | 0 |
| espn | 2026-11-17 22:51:01 | 19 | 0 |
| espn_elencos | 2026-11-17 04:30:23 | 3 | 0 |
| espn_historico | 2026-11-15 18:09:46 | 2 | 0 |
| espn_resumos | 2026-11-16 02:09:06 | 1 | 0 |
| espn_temporada | 2026-11-16 01:49:27 | 1 | 0 |
| estatisticas_brasil | 2026-11-17 05:35:06 | 3 | 0 |
| fdcouk | 2026-11-17 22:47:03 | 26 | 0 |
| fotmob_jogos | 2026-11-16 05:42:46 | 1 | 0 |
| fotmob_temporada | 2026-11-16 05:30:01 | 1 | 0 |
| lake | 2026-11-17 05:09:38 | 9 | 0 |
| open_matchday | 2026-11-17 15:34:27 | 9 | 0 |
| open_sources | 2026-11-17 04:41:48 | 5 | 0 |
| openfootball | 2026-11-17 04:32:10 | 6 | 0 |
| openplay | 2026-11-17 04:30:54 | 4 | 1 |
| simonetti | 2026-11-17 05:09:22 | 6 | 0 |
| statsbomb | 2026-11-17 04:30:50 | 6 | 0 |
| transfermarkt | 2026-11-17 05:07:26 | 8 | 0 |
| understat | 2026-11-17 05:08:29 | 7 | 0 |
| wyscout | 2026-11-17 04:30:53 | 6 | 0 |
