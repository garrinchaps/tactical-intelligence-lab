# Rodada 18 — publica o app do PC num link público GRÁTIS (Cloudflare Quick Tunnel: sem conta, sem cartão).
#
#   .\scripts\apresentar.ps1                  # pede a senha dos visitantes, liga o app e o túnel, mostra o link
#   .\scripts\apresentar.ps1 -Porta 8502      # outra porta, se a 8501 estiver ocupada
#   .\scripts\apresentar.ps1 -ComAtualizacao  # deixa a atualização automática ligada (mais lento para quem visita)
#
# A senha fica SÓ na memória desta janela (não vai para o .env, nem para arquivo, nem aparece na tela).
# Enquanto esta janela estiver aberta o link funciona; feche com Enter (desliga app e túnel juntos).
# No próprio PC continue usando http://localhost:<porta> — sem senha e com tudo liberado.

param(
    [int]$Porta = 8501,
    [switch]$ComAtualizacao
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$py = ".\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {
    foreach ($c in @("C:\Program Files (x86)\cloudflared\cloudflared.exe", "C:\Program Files\cloudflared\cloudflared.exe")) {
        if (Test-Path $c) { $cf = $c; break }
    }
}
if (-not $cf) {
    Write-Host "Falta o cloudflared. Instale com:  winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
    Write-Host "Depois feche e abra o terminal e rode este script de novo."
    exit 1
}

$busy = Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "A porta $Porta está ocupada (o app já está aberto?). Feche o app ou use -Porta 8502." -ForegroundColor Yellow
    exit 1
}

$sec = Read-Host "Senha para os visitantes (o professor vai digitar esta; não aparece na tela)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$env:TIL_SENHA = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
if ([string]::IsNullOrWhiteSpace($env:TIL_SENHA)) { Write-Host "Senha vazia — cancelado."; exit 1 }

if (-not $ComAtualizacao) { $env:AUTO_SYNC = "0" }     # só nesta janela: o app fica leve para quem visita

New-Item -ItemType Directory -Force -Path "data" | Out-Null
$log = "data\tunel.log"
if (Test-Path $log) { Remove-Item $log -Force }

Write-Host "Ligando o app na porta $Porta..."
$app = Start-Process -FilePath $py -PassThru -WindowStyle Minimized -ArgumentList @(
    "-m", "streamlit", "run", "app.py", "--server.port", "$Porta", "--server.headless", "true",
    "--browser.gatherUsageStats", "false")

$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    try { Invoke-WebRequest -UseBasicParsing "http://localhost:$Porta/_stcore/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch {}
}
if (-not $ok) { Write-Host "O app não respondeu em 90 s. Veja a janela minimizada do Python." -ForegroundColor Red; Stop-Process -Id $app.Id -ErrorAction SilentlyContinue; exit 1 }

Write-Host "Abrindo o túnel grátis da Cloudflare..."
$tun = Start-Process -FilePath $cf -PassThru -WindowStyle Hidden -RedirectStandardError $log -ArgumentList @(
    "tunnel", "--no-autoupdate", "--url", "http://localhost:$Porta")

$url = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value; break }
    }
}
if (-not $url) {
    Write-Host "O túnel não devolveu o link em 60 s (internet ou firewall?). Últimas linhas:" -ForegroundColor Red
    if (Test-Path $log) { Get-Content $log -Tail 8 }
    Stop-Process -Id $tun.Id -ErrorAction SilentlyContinue; Stop-Process -Id $app.Id -ErrorAction SilentlyContinue
    exit 1
}

try { Set-Clipboard -Value $url } catch {}
Write-Host ""
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host "  LINK PÚBLICO:  $url" -ForegroundColor Cyan
Write-Host "  (já copiado — cole no WhatsApp/e-mail do professor)"
Write-Host "  No seu PC continue em http://localhost:$Porta (sem senha)."
Write-Host "  O link muda cada vez que este script roda."
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Deixe esta janela aberta. Aperte Enter para DESLIGAR o link e o app"

Stop-Process -Id $tun.Id -ErrorAction SilentlyContinue
Stop-Process -Id $app.Id -ErrorAction SilentlyContinue
Remove-Item Env:\TIL_SENHA -ErrorAction SilentlyContinue
Write-Host "Desligado."
