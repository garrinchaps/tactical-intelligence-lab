# Rodadas 18–21 — publica o app do PC num link público GRÁTIS.
#
#   .\scripts\apresentar.ps1                       # link FIXO (Tailscale ou ngrok, se instalados) + contas individuais
#   .\scripts\apresentar.ps1 -Tunel tailscale      # força o Tailscale Funnel (https://SEU-PC.xxxx.ts.net — sempre igual)
#   .\scripts\apresentar.ps1 -Tunel ngrok          # força o ngrok (domínio grátis fixo da sua conta; mostra aviso 1ª vez)
#   .\scripts\apresentar.ps1 -Tunel cloudflare     # túnel rápido da Cloudflare (sem conta; o link MUDA a cada vez)
#   .\scripts\apresentar.ps1 -Dono seu@email.com   # entrando pelo link com este e-mail você vê o painel 👥 Contas
#   .\scripts\apresentar.ps1 -SenhaUnica           # modo antigo: uma senha só para todos (sem contas)
#   .\scripts\apresentar.ps1 -Porta 8502 -ComAtualizacao
#
# Contas: cada pessoa cria a sua (nome, e-mail, senha) usando o CÓDIGO DE CONVITE que você define aqui — ou entra com o
# Google, se você configurou (python -m src.tools.configurar_login). O código fica SÓ na memória desta janela.
# No próprio PC continue usando http://localhost:<porta> — sem login e com tudo liberado. Enter nesta janela desliga tudo.

param(
    [int]$Porta = 8501,
    [ValidateSet("auto", "tailscale", "ngrok", "cloudflare")][string]$Tunel = "auto",
    [string]$Dono = "",
    [switch]$SenhaUnica,
    [switch]$ComAtualizacao
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$py = ".\venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

function Find-Exe($name, $extra) {
    $c = (Get-Command $name -ErrorAction SilentlyContinue).Source
    if ($c) { return $c }
    foreach ($p in $extra) { if (Test-Path $p) { return $p } }
    return $null
}
$ts = Find-Exe "tailscale" @("C:\Program Files\Tailscale\tailscale.exe")
$ng = Find-Exe "ngrok" @("$env:LOCALAPPDATA\Microsoft\WinGet\Links\ngrok.exe")
$cf = Find-Exe "cloudflared" @("C:\Program Files (x86)\cloudflared\cloudflared.exe", "C:\Program Files\cloudflared\cloudflared.exe")
if ($Tunel -eq "auto") {
    if ($ts) { $Tunel = "tailscale" } elseif ($ng) { $Tunel = "ngrok" } else { $Tunel = "cloudflare" }
}
$need = @{ "tailscale" = $ts; "ngrok" = $ng; "cloudflare" = $cf }[$Tunel]
if (-not $need) {
    $how = @{ "tailscale" = "winget install --id Tailscale.Tailscale  (depois entre na conta e libere o Funnel)";
              "ngrok" = "winget install --id Ngrok.Ngrok  (depois: ngrok config add-authtoken SEU_TOKEN)";
              "cloudflare" = "winget install --id Cloudflare.cloudflared" }[$Tunel]
    Write-Host "Falta o programa do túnel ($Tunel). Instale com:  $how" -ForegroundColor Yellow
    exit 1
}

$busy = Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "A porta $Porta está ocupada (o app já está aberto?). Feche o app ou use -Porta 8502." -ForegroundColor Yellow
    exit 1
}

function Read-Secret($prompt) {
    $sec = Read-Host $prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    return $plain
}

if ($SenhaUnica) {
    $env:TIL_SENHA = Read-Secret "Senha única para os visitantes (não aparece na tela)"
    if ([string]::IsNullOrWhiteSpace($env:TIL_SENHA)) { Write-Host "Senha vazia — cancelado."; exit 1 }
} else {
    $env:TIL_CONTAS = "1"
    $env:TIL_CONVITE = Read-Secret "Código de convite para CRIAR conta (passe aos convidados; Enter = sem código)"
    if ($Dono) { $env:TIL_DONO_EMAIL = $Dono.Trim().ToLower() }
}

if (-not $ComAtualizacao) {
    $env:AUTO_SYNC = "0"          # só nesta janela: o app fica leve para quem visita
    $env:TIL_CONGELADO = "1"      # dados parados: o que foi aberto no ensaio continua pronto (cache em disco)
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null
$log = "data\tunel.log"
if (Test-Path $log) { Remove-Item $log -Force }

Write-Host "Ligando o app na porta $Porta..."
$app = Start-Process -FilePath $py -PassThru -WindowStyle Minimized -ArgumentList @(
    "-m", "streamlit", "run", "app.py", "--server.port", "$Porta", "--server.headless", "true",
    "--browser.gatherUsageStats", "false", "--server.enableWebsocketCompression", "true")

$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    try { Invoke-WebRequest -UseBasicParsing "http://localhost:$Porta/_stcore/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch {}
}
if (-not $ok) { Write-Host "O app não respondeu em 90 s. Veja a janela minimizada do Python." -ForegroundColor Red; Stop-Process -Id $app.Id -ErrorAction SilentlyContinue; exit 1 }

$tun = $null; $url = $null; $fixo = $true
if ($Tunel -eq "tailscale") {
    Write-Host "Abrindo o Tailscale Funnel (link fixo)..."
    & $ts funnel --bg $Porta | Out-Null
    $st = (& $ts status --json | ConvertFrom-Json)
    $dns = "$($st.Self.DNSName)".TrimEnd(".")
    if ($dns) { $url = "https://$dns" }
} elseif ($Tunel -eq "ngrok") {
    Write-Host "Abrindo o ngrok (domínio fixo da sua conta)..."
    $tun = Start-Process -FilePath $ng -PassThru -WindowStyle Hidden -ArgumentList @("http", "$Porta", "--log", "stdout") -RedirectStandardOutput $log
    for ($i = 0; $i -lt 30 -and -not $url; $i++) {
        Start-Sleep -Seconds 1
        try { $url = ((Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels").tunnels | Where-Object { $_.public_url -like "https*" } | Select-Object -First 1).public_url } catch {}
    }
} else {
    $fixo = $false
    Write-Host "Abrindo o túnel rápido da Cloudflare..."
    $tun = Start-Process -FilePath $cf -PassThru -WindowStyle Hidden -RedirectStandardError $log -ArgumentList @(
        "tunnel", "--no-autoupdate", "--url", "http://localhost:$Porta")
    for ($i = 0; $i -lt 60 -and -not $url; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value }
        }
    }
}
if (-not $url) {
    Write-Host "O túnel ($Tunel) não devolveu o link. Confira se o programa está logado/configurado." -ForegroundColor Red
    if (Test-Path $log) { Get-Content $log -Tail 8 }
    if ($tun) { Stop-Process -Id $tun.Id -ErrorAction SilentlyContinue }
    Stop-Process -Id $app.Id -ErrorAction SilentlyContinue
    exit 1
}

try { Set-Clipboard -Value $url } catch {}
Write-Host ""
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host "  LINK PÚBLICO:  $url" -ForegroundColor Cyan
Write-Host "  (já copiado)"
if ($fixo) { Write-Host "  Este link é SEMPRE o mesmo: mande uma vez só." } else { Write-Host "  Atenção: o link da Cloudflare muda a cada vez." }
if (-not $SenhaUnica) { Write-Host "  Cada pessoa cria a própria conta (com o código de convite) ou entra com o Google." }
Write-Host "  Quem criou conta: Bastidores › 👥 Contas (no PC, ou pelo link com o e-mail -Dono)."
Write-Host "  No seu PC continue em http://localhost:$Porta (sem login)."
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Deixe esta janela aberta. Aperte Enter para DESLIGAR o link e o app"

if ($Tunel -eq "tailscale") { & $ts funnel reset | Out-Null }
if ($tun) { Stop-Process -Id $tun.Id -ErrorAction SilentlyContinue }
Stop-Process -Id $app.Id -ErrorAction SilentlyContinue
foreach ($v in "TIL_SENHA", "TIL_CONVITE", "TIL_CONTAS", "TIL_DONO_EMAIL") { Remove-Item "Env:\$v" -ErrorAction SilentlyContinue }
Write-Host "Desligado."
