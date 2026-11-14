# Agenda a atualização automática da base no Windows (roda mesmo com o app fechado).
#   - a cada 3 horas: jogos recentes (football-data.co.uk, API-Football, football-data.org, ESPN) + boxscores
#   - todo dia às 6h: sincronização completa (inclui catálogos StatsBomb e Wyscout)
# Uso (PowerShell, na pasta do projeto):  .\scripts\agendar_atualizacao.ps1
# Remover:  schtasks /Delete /TN TacticalLabRapido /F ; schtasks /Delete /TN TacticalLabDiario /F

$proj = (Get-Location).Path
$py = Join-Path $proj "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Não achei $py. Rode este script na pasta do projeto, com o venv criado."; exit 1 }

schtasks /Create /F /SC HOURLY /MO 3 /TN "TacticalLabRapido" /TR "cmd /c cd /d `"$proj`" && `"$py`" -m src.data_hub.sync --rapido >> data\sync_log.txt 2>&1"
schtasks /Create /F /SC DAILY /ST 06:00 /TN "TacticalLabDiario" /TR "cmd /c cd /d `"$proj`" && `"$py`" -m src.data_hub.sync --days 3 --seasons 0 >> data\sync_log.txt 2>&1"
Write-Host "Pronto. Tarefas criadas: TacticalLabRapido (a cada 3 h) e TacticalLabDiario (6h)."
