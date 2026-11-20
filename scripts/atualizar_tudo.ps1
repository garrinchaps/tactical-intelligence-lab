# Rodada 23 — roda TUDO o que ficou faltando, em ordem, com o app FECHADO. Pode rodar de novo quando quiser:
# cada etapa continua de onde parou e não baixa de novo o que já veio.
#
#   .\scripts\atualizar_tudo.ps1            # tudo (pode levar de 30 min a algumas horas na 1ª vez)
#   .\scripts\atualizar_tudo.ps1 -Rapido    # só código + resultados recentes + Scout (uns 10–20 min)

param([switch]$Rapido)

$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = ".\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$busy = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($busy) { Write-Host "Feche o app (porta 8501 ocupada) e rode de novo: o banco aceita um gravador por vez." -ForegroundColor Yellow; exit 1 }

function Step($title, [scriptblock]$cmd) {
    $t = Get-Date
    Write-Host ""
    Write-Host "==> $title" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { Write-Host "    (terminou com aviso — sigo para a próxima etapa)" -ForegroundColor Yellow }
    Write-Host ("    feito em {0:N0} s" -f ((Get-Date) - $t).TotalSeconds)
}

Step "1. Código novo do GitHub" { git pull --ff-only }
Step "2. Dependências (só instala o que faltar)" { & $py -m pip install -q -r requirements.txt }
Step "3. Atualização automática sem janela (ao ligar, a cada 3 h e às 6h)" { powershell -ExecutionPolicy Bypass -File .\scripts\agendar_atualizacao.ps1 }
Step "4. Índices de velocidade do banco (só cria os que faltam)" { & $py -m src.tools.criar_indices }
Step "5. Resultados dos dias que faltam + detalhes desses jogos" { & $py -c "from src.tools.sync_silencioso import catch_up; print(catch_up())" }
if (-not $Rapido) {
    Step "6. Elencos (idade, país, valor) do Brasil e da América do Sul" { & $py -m src.data_hub.sync --only fotmob_elencos --ligas brasil sulamericanas }
    Step "7. Estatísticas dos jogos das Séries A, B e C" { & $py -m src.data_hub.sync --only fotmob_jogos --ligas brasil --limite 3000 }
    Step "8. Estatísticas das ligas sul-americanas" { & $py -m src.data_hub.sync --only fotmob_jogos --ligas sulamericanas --limite 2000 }
    Step "9a. Calendário das seleções de base (Mundiais, Sul-Americano, Euros, Ásia, CONCACAF, Toulon, Olimpíadas; 5 anos)" { & $py -m src.data_hub.sync --only fotmob_temporada --ligas base --temporadas 5 }
    Step "9b. Detalhes dos jogos de base (números por jogador de cada jogo; retomável)" { & $py -m src.data_hub.sync --only fotmob_jogos --ligas base --temporadas 5 --limite 5000 }
    Step "10. Apelidos de times entre fontes" { & $py -m src.data_hub.team_alias }
    Step "11. Rankings (avaliação de jogadores)" { & $py -m src.scout.evaluation }
}
Step "12. Scout (overall, potencial, atributos)" { & $py -m src.scout.snapshot }
Step "13. Cobertura do Scout por liga (docs\COBERTURA_SCOUT.md)" { & $py -m src.tools.cobertura_scout }
Step "14. Tamanho que a base núcleo teria (só informa)" { & $py -m src.tools.publicar_nucleo --tamanho }
Write-Host ""
Write-Host "Tudo pronto. Abra o app: streamlit run app.py" -ForegroundColor Green
