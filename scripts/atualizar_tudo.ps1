# Rodada 23 — roda TUDO o que ficou faltando, em ordem, com o app FECHADO. Pode rodar de novo quando quiser:
# cada etapa continua de onde parou e não baixa de novo o que já veio.
#
#   .\scripts\atualizar_tudo.ps1            # tudo (pode levar de 30 min a algumas horas na 1ª vez)
#   .\scripts\atualizar_tudo.ps1 -Rapido    # só código + resultados recentes + Scout (uns 10–20 min)
#   .\scripts\atualizar_tudo.ps1 -Tudo      # força TODAS as etapas, mesmo as feitas há pouco
#
# Rodada 27: cada etapa lembra quando foi feita (data\atualizacao_passos.json) e só roda quando VENCE — elencos e
# calendário de base 1×/semana, estatísticas e Rankings 1×/dia, Scout a cada 6 h, dependências só quando o
# requirements.txt muda. Rodar de novo no mesmo dia leva poucos minutos.

param([switch]$Rapido, [switch]$Tudo)

$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = ".\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$busy = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($busy) { Write-Host "Feche o app (porta 8501 ocupada) e rode de novo: o banco aceita um gravador por vez." -ForegroundColor Yellow; exit 1 }

# rodada 25c: "database is locked" em todas as etapas = outro processo DO LABORATÓRIO gravando ao mesmo tempo (processo
# de fundo que sobrou do app, ou a atualização automática agendada). 1) marca que a atualização manual está rodando
# (as tarefas automáticas e o processo de fundo saem do caminho); 2) encerra só os Python DESTA pasta; 3) espera o
# banco ficar livre.
New-Item -ItemType Directory -Force -Path data | Out-Null
Set-Content -Path data\atualizacao_manual.lock -Value $PID
$proj = (Get-Location).Path
$mine = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and ($_.CommandLine -like "*$proj*" -or $_.CommandLine -match "src\.(data_hub|tools|scout)\.") }
foreach ($p in $mine) {
    Write-Host ("Encerrando processo de fundo do laboratório (PID {0})" -f $p.ProcessId) -ForegroundColor DarkYellow
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
& $py -m src.tools.esperar_banco --max 300
if ($LASTEXITCODE -ne 0) { Remove-Item data\atualizacao_manual.lock -ErrorAction SilentlyContinue; exit 1 }

function Step($title, [scriptblock]$cmd, [string]$name = "", [double]$every = 0) {
    $t = Get-Date
    Write-Host ""
    Write-Host "==> $title" -ForegroundColor Cyan
    if ($name -and $every -gt 0 -and -not $Tudo) {
        & $py -m src.tools.passos --vencido $name --horas $every
        if ($LASTEXITCODE -eq 10) { return }
    }
    & $cmd
    $code = $LASTEXITCODE
    if ($code -and $code -ne 0) { Write-Host "    (terminou com aviso — sigo para a próxima etapa)" -ForegroundColor Yellow }
    elseif ($name) { & $py -m src.tools.passos --feito $name | Out-Null }
    Write-Host ("    feito em {0:N0} s" -f ((Get-Date) - $t).TotalSeconds)
}

try {
    Step "1. Código novo do GitHub" { git pull --ff-only }
    Step "2. Dependências (só quando o requirements.txt muda)" { & $py -m src.tools.passos --mudou requirements.txt; if ($LASTEXITCODE -eq 0 -or $Tudo) { & $py -m pip install -q -r requirements.txt } else { Write-Host "    pulado: requirements.txt igual"; $global:LASTEXITCODE = 0 } }
    Step "3. Limpeza (caches, fotografias antigas, registros grandes, temporários; banco otimizado sem apagar dados)" { & $py -m src.tools.limpeza } "limpeza" 24
    Step "4. Índices de velocidade do banco (só cria os que faltam)" { & $py -m src.tools.criar_indices } "indices" 168
    Step "5. Resultados dos dias que faltam + detalhes desses jogos" { & $py -c "from src.tools.sync_silencioso import catch_up; print(catch_up())" }
    if (-not $Rapido) {
        Step "6. Elencos (idade, país, valor) do Brasil e da América do Sul" { & $py -m src.data_hub.sync --only fotmob_elencos --ligas brasil sulamericanas } "elencos" 168
        Step "7. Estatísticas dos jogos das Séries A, B e C" { & $py -m src.data_hub.sync --only fotmob_jogos --ligas brasil --limite 3000 } "jogos_brasil" 20
        Step "8. Estatísticas das ligas sul-americanas" { & $py -m src.data_hub.sync --only fotmob_jogos --ligas sulamericanas --limite 2000 } "jogos_sulamericanas" 20
        Step "9a. Calendário das seleções de base (Mundiais, Sul-Americano, Euros, Ásia, CONCACAF, Toulon, Olimpíadas, amistosos Sub-21, Premier League Sub-18; 5 anos)" { & $py -m src.data_hub.sync --only fotmob_temporada --ligas base --temporadas 5 } "base_calendario" 168
        Step "9b. Detalhes de TODOS os jogos de base (números por jogador de cada jogo; retomável)" { & $py -m src.data_hub.sync --only fotmob_jogos --ligas base --temporadas 5 --limite 20000 } "base_jogos" 20
        Step "10. Apelidos de times entre fontes" { & $py -m src.data_hub.team_alias } "apelidos" 24
        Step "11. Rankings (avaliação de jogadores)" { & $py -m src.scout.evaluation } "rankings" 20
    }
    Step "12. Scout (overall, potencial, atributos)" { & $py -m src.scout.snapshot } "scout" 6
    Step "13. Cobertura do Scout por liga (docs\COBERTURA_SCOUT.md)" { & $py -m src.tools.cobertura_scout } "cobertura" 168
    Step "14. Tamanho que a base núcleo teria (só informa)" { & $py -m src.tools.publicar_nucleo --tamanho } "nucleo" 168
    Step "15. Atualização automática sem janela (ao ligar, a cada 3 h e às 6h) — agendada no fim para não disputar o banco" { powershell -ExecutionPolicy Bypass -File .\scripts\agendar_atualizacao.ps1 } "agendar" 168
} finally {
    Remove-Item data\atualizacao_manual.lock -ErrorAction SilentlyContinue   # libera as tarefas automáticas
}
Write-Host ""
Write-Host "Tudo pronto. Abra o app: streamlit run app.py" -ForegroundColor Green
