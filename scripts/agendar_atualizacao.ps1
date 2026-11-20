# Rodada 22 — atualização automática da base com o app FECHADO, SEM abrir janela de cmd.
#
#   .\scripts\agendar_atualizacao.ps1            # cria (ou recria) as tarefas silenciosas
#   .\scripts\agendar_atualizacao.ps1 -Remover   # apaga todas as tarefas do laboratório (antigas e novas)
#
# A versão antiga usava "cmd /c ..." e o Windows abria uma janela preta a cada 3 h. Agora a tarefa chama pythonw.exe
# (Python sem janela). Com o app aberto a tarefa não faz nada: o próprio app já atualiza em segundo plano.

param([switch]$Remover)

$proj = Split-Path -Parent $PSScriptRoot
$names = @("TacticalLabRapido", "TacticalLabDiario", "TacticalLabSync", "TacticalLabAoLigar")
foreach ($n in $names) {
    if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $n -Confirm:$false
        Write-Host "Removida a tarefa antiga: $n"
    }
}
if ($Remover) { Write-Host "Pronto: nenhuma atualização agendada do laboratório."; exit 0 }

$pyw = Join-Path $proj "venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { Write-Host "Não achei $pyw (o venv existe?)." -ForegroundColor Yellow; exit 1 }

$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$a1 = New-ScheduledTaskAction -Execute $pyw -Argument "-m src.tools.sync_silencioso --rapido" -WorkingDirectory $proj
$t1 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10) -RepetitionInterval (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName "TacticalLabRapido" -Action $a1 -Trigger $t1 -Settings $set `
        -Description "Tactical Lab: jogos recentes a cada 3 h (sem janela; pula se o app estiver aberto)" | Out-Null
# rodada 23: às 6h a tarefa ACORDA o PC se ele estiver em suspensão/hibernação (desligado de vez, nada roda)
$setWake = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -WakeToRun
$a2 = New-ScheduledTaskAction -Execute $pyw -Argument "-m src.tools.sync_silencioso --diario" -WorkingDirectory $proj
$t2 = New-ScheduledTaskTrigger -Daily -At 6am
Register-ScheduledTask -TaskName "TacticalLabDiario" -Action $a2 -Trigger $t2 -Settings $setWake `
        -Description "Tactical Lab: atualização diária às 6h (sem janela; acorda o PC da suspensão)" | Out-Null
# rodada 23: 2 min depois de entrar no Windows recupera os dias em que o PC ficou desligado (antes de você abrir o app)
$a3 = New-ScheduledTaskAction -Execute $pyw -Argument "-m src.tools.sync_silencioso --ao-ligar" -WorkingDirectory $proj
$t3 = New-ScheduledTaskTrigger -AtLogOn
$t3.Delay = "PT2M"
Register-ScheduledTask -TaskName "TacticalLabAoLigar" -Action $a3 -Trigger $t3 -Settings $set `
        -Description "Tactical Lab: ao entrar no Windows, busca os resultados dos dias com o PC desligado" | Out-Null
Write-Host "Pronto. Tarefas silenciosas: TacticalLabRapido (3 h), TacticalLabDiario (6h, acorda o PC) e TacticalLabAoLigar."
Write-Host "Com o app aberto elas não fazem nada (o próprio app atualiza). Registro: data\sync_log.txt"
