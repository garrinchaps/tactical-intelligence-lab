# Cobertura da base — Tactical Intelligence Lab

Gerado em 15/11/2026 16:12 a partir de `tactical_lab.db` · **310.275 partidas reais** (simulações e uploads fora da conta).


> Honestidade técnica: estes números saem direto do banco. Ligas e temporadas que não aparecem aqui **não estão em nenhuma fonte aberta sincronizada** — são lacunas reais, não zeros estimados.

## Níveis de dado

- **EVENTOS** — lances com coordenadas (passes, chutes, duelos): análise espacial completa.
- **ESTATÍSTICAS** — estatísticas de equipe (chutes, no alvo, posse, escanteios, faltas, cartões).
- **SÓ PLACAR** — placar e, quando a fonte traz, autores dos gols e escalações. Sem estatísticas.

## Visão geral

| nível | partidas | % |
|---|---|---|
| ESTATÍSTICAS | 64388 | 21% |
| EVENTOS | 32449 | 10% |
| SÓ PLACAR | 213438 | 69% |

## Inconsistências detectadas

Nenhuma.

## Por fonte

| fonte | ESTATÍSTICAS | EVENTOS | SÓ PLACAR | total |
|---|---|---|---|---|
| fdcouk | 59176 | 0 | 67063 | 126239 |
| openfootball | 0 | 0 | 89781 | 89781 |
| intl | 0 | 0 | 49923 | 49923 |
| openplay | 0 | 26547 | 0 | 26547 |
| brasileirao | 3410 | 0 | 5375 | 8785 |
| statsbomb | 0 | 3961 | 0 | 3961 |
| open_matchday | 1802 | 0 | 1296 | 3098 |
| wyscout | 0 | 1941 | 0 | 1941 |

## Preenchimento de campos

| campo | preenchido | base |
|---|---|---|
| data | 100% | todas as partidas |
| país | 91% | todas as partidas |
| rodada | 34% | todas as partidas |
| estádio | 20% | todas as partidas |
| árbitro | 7% | todas as partidas |
| linha do tempo (gols/cartões) | 7% | todas as partidas |
| escalações | 0% | todas as partidas |
| estatística: chutes | 98% | 64388 partidas com estatísticas |
| estatística: no alvo | 95% | 64388 partidas com estatísticas |
| estatística: posse | 5% | 64388 partidas com estatísticas |
| estatística: escanteios | 98% | 64388 partidas com estatísticas |
| estatística: faltas | 96% | 64388 partidas com estatísticas |
| estatística: amarelos | 100% | 64388 partidas com estatísticas |
| estatística: xG | 0% | 64388 partidas com estatísticas |
| eventos já baixados | 0% | 32449 partidas com eventos na fonte |

## Por competição e temporada (maiores 400)

`estatísticas ausentes` lista, para os jogos com estatísticas, quais indicadores nenhuma partida daquela temporada traz (`n/a` = não há jogos com estatísticas).


| competição | temporada | partidas | EVENTOS | eventos em disco | ESTATÍSTICAS | SÓ PLACAR | fontes | estatísticas ausentes |
|---|---|---|---|---|---|---|---|---|
| La Liga | 2017/2018 | 1175 | 796 | 0 | 379 | 0 | fdcouk, openplay, statsbomb, wyscout | posse, xG |
| Serie A | 2017/2018 | 1140 | 760 | 0 | 380 | 0 | fdcouk, openplay, wyscout | posse, xG |
| Ligue 1 | 2017/2018 | 1140 | 760 | 0 | 380 | 0 | fdcouk, openplay, wyscout | posse, xG |
| Premier League | 2017/2018 | 1139 | 760 | 0 | 379 | 0 | fdcouk, openplay, wyscout | posse, xG |
| Campeonato Brasileiro Série A | 2021 | 872 | 0 | 0 | 492 | 380 | brasileirao, fdcouk | xG |
| La Liga | 2020/2021 | 795 | 415 | 11 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| La Liga | 2018/2019 | 794 | 414 | 1 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| La Liga | 2016/2017 | 794 | 414 | 0 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| La Liga | 2019/2020 | 792 | 413 | 0 | 379 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| Ligue 1 | 2022/2023 | 790 | 411 | 0 | 379 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| Ligue 1 | 2021/2022 | 781 | 401 | 0 | 380 | 0 | fdcouk, openplay, statsbomb | posse, xG |
| Premier League | 2016/2017 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2015/2016 | 760 | 760 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| Premier League | 2020/2021 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2020/2021 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2024 | 760 | 0 | 0 | 1 | 759 | brasileirao, fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2013 | 760 | 0 | 0 | 0 | 760 | brasileirao, fdcouk | n/a |
| Premier League | 2018/2019 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2024/2025 | 760 | 380 | 1 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2023/2024 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2018/2019 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2023/2024 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2015/2016 | 760 | 760 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| Premier League | 2022/2023 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2025/2026 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2025/2026 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2015/2016 | 760 | 760 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| La Liga | 2022/2023 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2024/2025 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2020/2021 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2018 | 760 | 0 | 0 | 380 | 380 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2022 | 760 | 0 | 0 | 380 | 380 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2017 | 760 | 0 | 0 | 379 | 381 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2014 | 760 | 0 | 0 | 17 | 743 | brasileirao, fdcouk | xG |
| Serie A | 2016/2017 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2019/2020 | 760 | 380 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2023/2024 | 759 | 380 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2023 | 759 | 0 | 0 | 380 | 379 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2015 | 759 | 0 | 0 | 382 | 377 | brasileirao, fdcouk | xG |
| Campeonato Brasileiro Série A | 2012 | 759 | 0 | 0 | 1 | 758 | brasileirao, fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2019 | 759 | 0 | 0 | 358 | 401 | brasileirao, fdcouk | xG |
| Ligue 1 | 2018/2019 | 759 | 380 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2016/2017 | 759 | 379 | 0 | 379 | 1 | fdcouk, openplay | posse, xG |
| Campeonato Brasileiro Série A | 2016 | 758 | 0 | 0 | 379 | 379 | brasileirao, fdcouk | xG |
| Serie A | 2024/2025 | 758 | 380 | 0 | 378 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2025/2026 | 758 | 380 | 0 | 378 | 0 | fdcouk, openplay | posse, xG |
| Premier League | 2019/2020 | 758 | 379 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| La Liga | 2021/2022 | 758 | 379 | 0 | 379 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2015/2016 | 757 | 757 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| Premier League | 2021/2022 | 757 | 377 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2022/2023 | 755 | 375 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Serie A | 2021/2022 | 754 | 374 | 0 | 380 | 0 | fdcouk, openplay | posse, xG |
| Major League Soccer | 2025 | 704 | 0 | 0 | 0 | 704 | fdcouk, openfootball | n/a |
| Campeonato Brasileiro Série A | 2020 | 648 | 0 | 0 | 267 | 381 | brasileirao, fdcouk | xG |
| Bundesliga | 2016/2017 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2024/2025 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2017/2018 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2018/2019 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2019/2020 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2025/2026 | 612 | 306 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2024/2025 | 611 | 306 | 0 | 304 | 1 | fdcouk, openplay | posse, xG |
| Bundesliga | 2020/2021 | 611 | 306 | 0 | 305 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2025/2026 | 611 | 306 | 0 | 305 | 0 | fdcouk, openplay | posse, xG |
| Ligue 1 | 2023/2024 | 611 | 305 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2021/2022 | 611 | 306 | 0 | 305 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2023/2024 | 611 | 306 | 0 | 305 | 0 | fdcouk, openplay | posse, xG |
| Bundesliga | 2022/2023 | 610 | 304 | 0 | 306 | 0 | fdcouk, openplay | posse, xG |
| FIFA World Cup qualification | 2021 | 609 | 0 | 0 | 0 | 609 | intl | n/a |
| Ligue 1 | 2019/2020 | 558 | 279 | 0 | 279 | 0 | fdcouk, openplay | posse, xG |
| English Championship | 2021/22 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| English Championship | 2022/23 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| English Championship | 2025/26 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| English Championship | 2024/25 | 557 | 0 | 0 | 0 | 557 | openfootball | n/a |
| English Championship | 2023/24 | 556 | 0 | 0 | 0 | 556 | openfootball | n/a |
| League One | 2024/2025 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| League Two | 2024/2025 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2021/2022 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| National League | 2025/2026 | 552 | 0 | 0 | 552 | 0 | fdcouk | chutes, no alvo, posse, escanteios, faltas, xG |
| English League Two | 2020/21 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| Championship | 2024/2025 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2003 | 552 | 0 | 0 | 0 | 552 | brasileirao | n/a |
| Championship | 2016/2017 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2017/2018 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Campeonato Brasileiro Série A | 2004 | 552 | 0 | 0 | 0 | 552 | brasileirao | n/a |
| Championship | 2019/2020 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2022/2023 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| Championship | 2023/2024 | 552 | 0 | 0 | 552 | 0 | fdcouk | posse, xG |
| English League One | 2011/12 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2012/13 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2019/20 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2020/21 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2014/15 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2011/12 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2013/14 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League Two | 2018/19 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2024/25 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2020/21 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2013/14 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2015/16 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English League One | 2018/19 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2012/13 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2013/14 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2015/16 | 552 | 0 | 0 | 0 | 552 | openfootball | n/a |
| English Championship | 2014/15 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| National League | 2024/2025 | 551 | 0 | 0 | 551 | 0 | fdcouk | chutes, no alvo, posse, escanteios, faltas, xG |
| Championship | 2018/2019 | 551 | 0 | 0 | 550 | 1 | fdcouk | posse, xG |
| Championship | 2020/2021 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| Championship | 2025/2026 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| League Two | 2025/2026 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| English League One | 2014/15 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League Two | 2012/13 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| League One | 2025/2026 | 551 | 0 | 0 | 551 | 0 | fdcouk | posse, xG |
| English Championship | 2018/19 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League Two | 2024/25 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League One | 2010/11 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English Championship | 2010/11 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English Championship | 2011/12 | 551 | 0 | 0 | 0 | 551 | openfootball | n/a |
| English League Two | 2015/16 | 550 | 0 | 0 | 0 | 550 | openfootball | n/a |
| English League Two | 2010/11 | 549 | 0 | 0 | 0 | 549 | openfootball | n/a |
| Major League Soccer | 2023 | 527 | 6 | 0 | 0 | 521 | fdcouk, statsbomb | n/a |
| Major League Soccer | 2024 | 522 | 0 | 0 | 0 | 522 | fdcouk | n/a |
| Liga Profesional | 2025 | 510 | 0 | 0 | 0 | 510 | fdcouk | n/a |
| Major League Soccer | 2026 | 510 | 0 | 0 | 1 | 509 | fdcouk | posse, xG |
| Bundesliga | 2025/26 | 501 | 0 | 0 | 0 | 501 | openfootball | n/a |
| Liga Profesional | 2026 | 494 | 0 | 0 | 1 | 493 | fdcouk | posse, xG |
| FIFA World Cup qualification | 2025 | 492 | 0 | 0 | 0 | 492 | intl | n/a |
| FIFA World Cup qualification | 2001 | 491 | 0 | 0 | 0 | 491 | intl | n/a |
| Major League Soccer | 2022 | 489 | 0 | 0 | 0 | 489 | fdcouk | n/a |
| Italian Serie B | 2017/18 | 472 | 0 | 0 | 0 | 472 | openfootball | n/a |
| Italian Serie B | 2014/15 | 472 | 0 | 0 | 0 | 472 | openfootball | n/a |
| Italian Serie B | 2015/16 | 472 | 0 | 0 | 0 | 472 | openfootball | n/a |
| Major League Soccer | 2021 | 471 | 0 | 0 | 0 | 471 | fdcouk | n/a |
| Italian Serie B | 2013/14 | 471 | 0 | 0 | 0 | 471 | openfootball | n/a |
| Italian Serie B | 2016/17 | 469 | 0 | 0 | 0 | 469 | openfootball | n/a |
| Liga Profesional  (Argentina) | 2015 | 468 | 0 | 0 | 1 | 467 | fdcouk | posse, xG |
| La Liga 2 | 2018/2019 | 462 | 0 | 0 | 441 | 21 | fdcouk | posse, xG |
| La Liga 2 | 2017/2018 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| Segunda División de España | 2014/15 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2016/17 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2017/18 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2015/16 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Segunda División de España | 2020/21 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| La Liga 2 | 2025/2026 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2021/2022 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2022/2023 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2019/2020 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2024/2025 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2016/2017 | 462 | 0 | 0 | 0 | 462 | fdcouk | n/a |
| Segunda División de España | 2019/20 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Campeonato Brasileiro Série A | 2005 | 462 | 0 | 0 | 0 | 462 | brasileirao | n/a |
| Serie B | 2017/2018 | 462 | 0 | 0 | 462 | 0 | fdcouk | posse, xG |
| Segunda División de España | 2012/13 | 462 | 0 | 0 | 0 | 462 | openfootball | n/a |
| Serie B | 2016/2017 | 461 | 0 | 0 | 0 | 461 | fdcouk | n/a |
| La Liga 2 | 2020/2021 | 461 | 0 | 0 | 461 | 0 | fdcouk | posse, xG |
| La Liga 2 | 2023/2024 | 461 | 0 | 0 | 461 | 0 | fdcouk | posse, xG |
| Segunda División de España | 2013/14 | 461 | 0 | 0 | 0 | 461 | openfootball | n/a |
| Segunda División de España | 2018/19 | 461 | 0 | 0 | 0 | 461 | openfootball | n/a |
| Spain Segunda División | 2024/25 | 452 | 0 | 0 | 0 | 452 | openfootball | n/a |
| Liga Profesional  (Argentina) | 2016/2017 | 450 | 0 | 0 | 0 | 450 | fdcouk | n/a |
| English League Two | 2019/20 | 440 | 0 | 0 | 0 | 440 | openfootball | n/a |
| Friendly | 2010 | 422 | 0 | 0 | 0 | 422 | intl | n/a |
| Major League Soccer | 2019 | 421 | 0 | 0 | 0 | 421 | fdcouk | n/a |
| Süper Lig | 2020/2021 | 420 | 0 | 0 | 420 | 0 | fdcouk | posse, xG |
| Turkish Süper Lig | 2020/21 | 420 | 0 | 0 | 0 | 420 | openfootball | n/a |
| Friendly | 2018 | 420 | 0 | 0 | 0 | 420 | intl | n/a |
| La Liga | 2014/2015 | 418 | 418 | 0 | 0 | 0 | openplay, statsbomb | n/a |
| FIFA World Cup qualification | 2008 | 414 | 0 | 0 | 0 | 414 | intl | n/a |
| FIFA World Cup qualification | 1997 | 410 | 0 | 0 | 0 | 410 | intl | n/a |
| Major League Soccer | 2018 | 408 | 0 | 0 | 0 | 408 | fdcouk | n/a |
| FIFA World Cup qualification | 2004 | 408 | 0 | 0 | 0 | 408 | intl | n/a |
| Friendly | 2008 | 407 | 0 | 0 | 0 | 407 | intl | n/a |
| Friendly | 2012 | 406 | 0 | 0 | 0 | 406 | intl | n/a |
| English League One | 2019/20 | 398 | 0 | 0 | 0 | 398 | openfootball | n/a |
| Italian Serie B | 2019/20 | 390 | 0 | 0 | 0 | 390 | openfootball | n/a |
| Major League Soccer | 2017 | 390 | 0 | 0 | 0 | 390 | fdcouk | n/a |
| Italian Serie B | 2020/21 | 388 | 0 | 0 | 0 | 388 | openfootball | n/a |
| Italian Serie B | 2024/25 | 387 | 0 | 0 | 0 | 387 | openfootball | n/a |
| Friendly | 2014 | 384 | 0 | 0 | 0 | 384 | intl | n/a |
| Liga Profesional  (Argentina) | 2013/2014 | 382 | 0 | 0 | 0 | 382 | fdcouk | n/a |
| Liga Profesional  (Argentina) | 2012/2013 | 381 | 0 | 0 | 0 | 381 | fdcouk | n/a |
| Deutsche 3. Liga | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2011/12 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Serie B | 2025/2026 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Serie B | 2024/2025 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Premier League | 2014/2015 | 380 | 380 | 0 | 0 | 0 | openplay | n/a |
| Deutsche 3. Liga | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Spain Primera División | 2025/26 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Deutsche 3. Liga | 2019/20 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Campeonato Brasileiro Série A | 2007 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| French Ligue 2 | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2019/20 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Campeonato Brasileiro Série A | 2008 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Campeonato Brasileiro Série A | 2009 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Ligue 1 | 2014/2015 | 380 | 380 | 0 | 0 | 0 | openplay | n/a |
| Brasileiro Série A | 2019 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Campeonato Brasileiro Série B | 2026/2027 | 380 | 0 | 0 | 0 | 380 | open_matchday | n/a |
| Campeonato Brasileiro Série A | 2010 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Campeonato Brasileiro Série A | 2011 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| Primera División de España | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2013/14 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileiro Série A | 2025 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Brasileiro Série A | 2020 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2013/14 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Serie B | 2021/2022 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| English Premier League | 2013/14 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2021/22 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2024/25 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2023/24 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Ligue 2 | 2022/2023 | 380 | 0 | 0 | 379 | 1 | fdcouk | posse, xG |
| English Premier League | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| J1 League (Japan) | 2021 | 380 | 0 | 0 | 0 | 380 | fdcouk | n/a |
| J1 League (Japan) | 2024 | 380 | 0 | 0 | 0 | 380 | fdcouk | n/a |
| Serie A | 2014/2015 | 380 | 380 | 0 | 0 | 0 | openplay | n/a |
| Campeonato Brasileiro Série A | 2006 | 380 | 0 | 0 | 0 | 380 | brasileirao | n/a |
| French Ligue 1 | 2017/18 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Campeonato Brasileiro Série A | 2025 | 380 | 0 | 0 | 0 | 380 | fdcouk | n/a |
| French Ligue 1 | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2019/20 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2023/24 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2014/15 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Primera División de España | 2020/21 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2021/22 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 2 | 2016/17 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2023/24 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2025/26 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Ligue 2 | 2017/2018 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, faltas, xG |
| Ligue 2 | 2020/2021 | 380 | 0 | 0 | 379 | 1 | fdcouk | posse, xG |
| English Premier League | 2018/19 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Italian Serie A | 2021/22 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Premier League | 2025/26 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2010/11 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| Serie B | 2023/2024 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Serie B | 2022/2023 | 380 | 0 | 0 | 380 | 0 | fdcouk | posse, xG |
| Serie B | 2020/2021 | 380 | 0 | 0 | 379 | 1 | fdcouk | posse, xG |
| English Premier League | 2022/23 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| English Premier League | 2015/16 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| J1 League (Japan) | 2025 | 380 | 0 | 0 | 1 | 379 | fdcouk | posse, xG |
| English Premier League | 2012/13 | 380 | 0 | 0 | 0 | 380 | openfootball | n/a |
| French Ligue 1 | 2016/17 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Ligue 2 | 2021/2022 | 379 | 0 | 0 | 378 | 1 | fdcouk | posse, xG |
| Primera División de España | 2012/13 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| French Ligue 2 | 2018/19 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| French Ligue 1 | 2014/15 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Italian Serie A | 2020/21 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Ligue 2 | 2018/2019 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Serie B | 2019/2020 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Süper Lig | 2021/2022 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Italian Serie A | 2017/18 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Primera División de España | 2021/22 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Primera División de España | 2018/19 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Süper Lig | 2023/2024 | 379 | 0 | 0 | 378 | 1 | fdcouk | posse, xG |
| English Premier League | 2019/20 | 379 | 0 | 0 | 0 | 379 | openfootball | n/a |
| Ligue 2 | 2023/2024 | 379 | 0 | 0 | 379 | 0 | fdcouk | posse, xG |
| Deutsche 3. Liga | 2015/16 | 378 | 0 | 0 | 0 | 378 | openfootball | n/a |
| Liga Profesional | 2022 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| Liga Profesional | 2023 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| Liga Profesional | 2017/2018 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| English Premier League | 2016/17 | 378 | 0 | 0 | 0 | 378 | openfootball | n/a |
| Ligue 2 | 2016/2017 | 378 | 0 | 0 | 0 | 378 | fdcouk | n/a |
| Liga Profesional | 2024 | 377 | 0 | 0 | 0 | 377 | fdcouk | n/a |
| Friendly | 2011 | 374 | 0 | 0 | 0 | 374 | intl | n/a |
| Friendly | 2004 | 372 | 0 | 0 | 0 | 372 | intl | n/a |
| Italian Serie A | 2024/25 | 370 | 0 | 0 | 0 | 370 | openfootball | n/a |
| Spain Primera División | 2024/25 | 370 | 0 | 0 | 0 | 370 | openfootball | n/a |
| Friendly | 2000 | 362 | 0 | 0 | 0 | 362 | intl | n/a |
| Championship | 2026/2027 | 359 | 0 | 0 | 359 | 0 | fdcouk, open_matchday | posse, xG |
| Major League Soccer | 2016 | 357 | 0 | 0 | 0 | 357 | fdcouk | n/a |
| Major League Soccer | 2015 | 357 | 0 | 0 | 0 | 357 | fdcouk | n/a |
| English League One | 2025/26 | 356 | 0 | 0 | 0 | 356 | openfootball | n/a |
| Italian Serie B | 2018/19 | 352 | 0 | 0 | 0 | 352 | openfootball | n/a |
| FIFA World Cup qualification | 2005 | 351 | 0 | 0 | 0 | 351 | intl | n/a |
| Friendly | 2006 | 348 | 0 | 0 | 0 | 348 | intl | n/a |
| FIFA World Cup qualification | 2013 | 347 | 0 | 0 | 0 | 347 | intl | n/a |
| Friendly | 2002 | 347 | 0 | 0 | 0 | 347 | intl | n/a |
| Friendly | 2022 | 343 | 0 | 0 | 0 | 343 | intl | n/a |
| Serie B | 2018/2019 | 342 | 0 | 0 | 341 | 1 | fdcouk | posse, xG |
| Süper Lig | 2024/2025 | 342 | 0 | 0 | 341 | 1 | fdcouk | posse, xG |
| Liga MX | 2022/2023 | 342 | 0 | 0 | 0 | 342 | fdcouk | n/a |
| Liga MX | 2020/2021 | 342 | 0 | 0 | 0 | 342 | fdcouk | n/a |
| Liga MX | 2021/2022 | 342 | 0 | 0 | 0 | 342 | fdcouk | n/a |
| Liga MX | 2020/21 | 341 | 0 | 0 | 0 | 341 | openfootball | n/a |
| Campeonato Brasileiro Série A | 2026/2027 | 341 | 0 | 0 | 0 | 341 | open_matchday | n/a |
| Süper Lig | 2022/2023 | 341 | 0 | 0 | 313 | 28 | fdcouk | posse, xG |
| Liga MX | 2023/2024 | 340 | 0 | 0 | 0 | 340 | fdcouk | n/a |
| Liga MX | 2024/25 | 340 | 0 | 0 | 0 | 340 | openfootball | n/a |
| Liga MX | 2024/2025 | 340 | 0 | 0 | 0 | 340 | fdcouk | n/a |
| Campeonato Brasileiro Série A | 2026 | 339 | 0 | 0 | 0 | 339 | fdcouk | n/a |
| FIFA World Cup qualification | 1993 | 339 | 0 | 0 | 0 | 339 | intl | n/a |
| Major League Soccer | 2013 | 338 | 0 | 0 | 0 | 338 | fdcouk | n/a |
| League Two | 2026/2027 | 338 | 0 | 0 | 338 | 0 | fdcouk, open_matchday | posse, xG |
| Major League Soccer | 2012 | 338 | 0 | 0 | 0 | 338 | fdcouk | n/a |
| Major League Soccer | 2014 | 338 | 0 | 0 | 0 | 338 | fdcouk | n/a |
| Turkish Süper Lig | 2024/25 | 338 | 0 | 0 | 0 | 338 | openfootball | n/a |
| Liga MX | 2025/2026 | 336 | 0 | 0 | 0 | 336 | fdcouk | n/a |
| Liga MX | 2014/2015 | 334 | 0 | 0 | 0 | 334 | fdcouk | n/a |
| Liga MX | 2018/2019 | 334 | 0 | 0 | 0 | 334 | fdcouk | n/a |
| Liga MX | 2015/2016 | 334 | 0 | 0 | 0 | 334 | fdcouk | n/a |
| Liga MX | 2016/2017 | 334 | 0 | 0 | 1 | 333 | fdcouk | posse, xG |
| Liga MX | 2012/2013 | 334 | 0 | 0 | 0 | 334 | fdcouk | n/a |
| Liga MX | 2017/2018 | 334 | 0 | 0 | 1 | 333 | fdcouk | posse, xG |
| Liga MX | 2018/19 | 334 | 0 | 0 | 0 | 334 | openfootball | n/a |
| Liga MX | 2013/2014 | 333 | 0 | 0 | 0 | 333 | fdcouk | n/a |
| FIFA World Cup qualification | 2009 | 332 | 0 | 0 | 0 | 332 | intl | n/a |
| Belgium First Division A | 2020/21 | 330 | 0 | 0 | 0 | 330 | openfootball | n/a |
| Friendly | 2013 | 326 | 0 | 0 | 0 | 326 | intl | n/a |
| Friendly | 2007 | 326 | 0 | 0 | 0 | 326 | intl | n/a |
| Liga Profesional | 2021 | 325 | 0 | 0 | 0 | 325 | fdcouk | n/a |
| Argentina Primera Division | 2018/19 | 325 | 0 | 0 | 0 | 325 | openfootball | n/a |
| Major League Soccer | 2020 | 324 | 0 | 0 | 1 | 323 | fdcouk | posse, xG |
| Liga Profesional | 2018/2019 | 324 | 0 | 0 | 0 | 324 | fdcouk | n/a |
| League One | 2026/2027 | 321 | 0 | 0 | 321 | 0 | fdcouk, open_matchday | posse, xG |
| Superliga (Romania) | 2023/2024 | 321 | 0 | 0 | 0 | 321 | fdcouk | n/a |
| Superliga (Romania) | 2022/2023 | 321 | 0 | 0 | 0 | 321 | fdcouk | n/a |
| Superliga (Romania) | 2025/2026 | 321 | 0 | 0 | 0 | 321 | fdcouk | n/a |
| Superliga (Romania) | 2020/2021 | 321 | 0 | 0 | 0 | 321 | fdcouk | n/a |
| Superliga (Romania) | 2021/2022 | 320 | 0 | 0 | 0 | 320 | fdcouk | n/a |
| Friendly | 2009 | 319 | 0 | 0 | 0 | 319 | intl | n/a |
| Friendly | 2003 | 319 | 0 | 0 | 0 | 319 | intl | n/a |
| Superliga (Romania) | 2024/2025 | 315 | 0 | 0 | 0 | 315 | fdcouk | n/a |
| Belgium First Division A | 2024/25 | 313 | 0 | 0 | 0 | 313 | openfootball | n/a |
| Jupiler Pro League | 2024/2025 | 311 | 0 | 0 | 310 | 1 | fdcouk | posse, xG |
| Jupiler Pro League | 2023/2024 | 311 | 0 | 0 | 311 | 0 | fdcouk | posse, xG |
| FIFA World Cup qualification | 2017 | 311 | 0 | 0 | 0 | 311 | intl | n/a |
| Turkish 1. Lig | 2019/20 | 310 | 0 | 0 | 0 | 310 | openfootball | n/a |
| J1 League (Japan) | 2019 | 310 | 0 | 0 | 0 | 310 | fdcouk | n/a |
| Jupiler Pro League | 2025/2026 | 309 | 0 | 0 | 309 | 0 | fdcouk | posse, xG |
| J1 League (Japan) | 2022 | 309 | 0 | 0 | 1 | 308 | fdcouk | posse, xG |
| J1 League (Japan) | 2018 | 309 | 0 | 0 | 0 | 309 | fdcouk | n/a |
| J1 League (Japan) | 2016 | 309 | 0 | 0 | 0 | 309 | fdcouk | n/a |
| J1 League (Japan) | 2015 | 309 | 0 | 0 | 0 | 309 | fdcouk | n/a |
| Italian Serie B | 2025/26 | 309 | 0 | 0 | 0 | 309 | openfootball | n/a |
| Superliga (Romania) | 2012/2013 | 307 | 0 | 0 | 1 | 306 | fdcouk | posse, xG |
| Netherlands Eredivisie | 2021/22 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Netherlands Eredivisie | 2022/23 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| 2. Bundesliga | 2023/2024 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| 2. Bundesliga | 2022/2023 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| 2. Bundesliga | 2018/2019 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Deutsche 2. Bundesliga | 2012/13 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Czech Republic First League | 2020/21 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| 2. Bundesliga | 2025/2026 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| 2. Bundesliga | 2024/2025 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| 1. Bundesliga | 2017/2018 | 306 | 306 | 0 | 0 | 0 | wyscout | n/a |
| Deutsche 2. Bundesliga | 2020/21 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2019/20 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2018/19 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2021/22 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2017/18 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2013/14 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2014/15 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Deutsche 2. Bundesliga | 2016/17 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Portuguese Primeira Liga | 2018/19 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Netherlands Eredivisie | 2024/25 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Bundesliga | 2014/2015 | 306 | 306 | 0 | 0 | 0 | openplay | n/a |
| Bundesliga | 2015/2016 | 306 | 306 | 0 | 0 | 0 | openplay | n/a |
| Netherlands Eredivisie | 2023/24 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Netherlands Eredivisie | 2020/21 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Superliga (Romania) | 2014/2015 | 306 | 0 | 0 | 2 | 304 | fdcouk | posse, xG |
| Süper Lig | 2018/2019 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Super League (China) | 2022 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| J1 League (Japan) | 2013 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| J1 League | 2020 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| J1 League | 2019 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| J1 League (Japan) | 2014 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| J1 League (Japan) | 2017 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| J1 League (Japan) | 2020 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| J1 League (Japan) | 2023 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| Turkish Süper Lig | 2018/19 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Süper Lig | 2025/2026 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| French Ligue 1 | 2024/25 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Eredivisie | 2021/2022 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Eredivisie | 2023/2024 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Eredivisie | 2025/2026 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Süper Lig | 2016/2017 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| Primeira Liga | 2016/2017 | 306 | 0 | 0 | 0 | 306 | fdcouk | n/a |
| Primeira Liga | 2021/2022 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Primeira Liga | 2020/2021 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Primeira Liga | 2019/2020 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| Primeira Liga | 2023/2024 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |
| French Ligue 1 | 2023/24 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| French Ligue 2 | 2024/25 | 306 | 0 | 0 | 0 | 306 | openfootball | n/a |
| Süper Lig | 2017/2018 | 306 | 0 | 0 | 306 | 0 | fdcouk | posse, xG |

## Qualidade dos dados

- Partidas auditadas: 310275
- Bloqueadas pela validação (placar negativo, equipe vazia, data impossível): 0
- Avisos de data fora da temporada: 496
- Duplicatas reais (mesmo conteúdo SHA-256, mesma fonte, ids diferentes): 0
- Mesma partida presente em outra fonte (ligações esperadas): 46175
- Lances com minuto fora de 0–130: 0 · eventos fora do campo/minuto: 5


Primeiros avisos:


| match_id | fonte | aviso |
|---|---|---|
| 11001980554 | openplay | data 2026-08-12 fora da temporada 2025/2026 |
| 8842256121 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8638749168 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8447949663 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8192129599 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8165319128 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8123861949 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8107924724 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8095301781 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8067608929 | open_matchday | data 2026-05-31 fora da temporada 2026/2027 |
| 8778574153 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8556553603 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8547046388 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8449469801 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8370256454 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8368332595 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8346343716 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8330107234 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8269315882 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |
| 8102568931 | open_matchday | data 2026-05-30 fora da temporada 2026/2027 |

## Últimas sincronizações

| fonte | última | ok | erros |
|---|---|---|---|
| api_football | 2026-11-15 17:36:11 | 5 | 0 |
| brasileirao | 2026-11-15 17:41:35 | 2 | 0 |
| cbf | 2026-11-15 18:49:15 | 3 | 0 |
| espn | 2026-11-15 17:37:32 | 8 | 0 |
| espn_historico | 2026-11-15 18:09:46 | 2 | 0 |
| estatisticas_brasil | 2026-11-15 19:12:11 | 2 | 0 |
| fdcouk | 2026-11-15 17:41:15 | 13 | 0 |
| lake | 2026-11-15 18:49:17 | 8 | 0 |
| open_matchday | 2026-11-15 17:33:21 | 3 | 0 |
| open_sources | 2026-11-15 17:43:28 | 4 | 0 |
| openfootball | 2026-11-15 17:49:13 | 5 | 0 |
| openplay | 2026-11-15 17:51:33 | 3 | 1 |
| simonetti | 2026-11-15 17:52:08 | 5 | 0 |
| statsbomb | 2026-11-15 17:39:24 | 5 | 0 |
| transfermarkt | 2026-11-15 18:47:01 | 6 | 0 |
| understat | 2026-11-15 18:47:54 | 6 | 0 |
| wyscout | 2026-11-15 17:39:25 | 5 | 0 |
