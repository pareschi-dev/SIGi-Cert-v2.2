$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$FrontendModules = Join-Path $FrontendDir "node_modules"
$FrontendDist = Join-Path $FrontendDir "dist"
$SiteUrl = "http://127.0.0.1:8000"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "O comando '$Command $($Arguments -join ' ')' falhou com código $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host "=== Iniciando SIGi Certidões ===" -ForegroundColor Cyan

if (-not (Test-Path $VenvPython)) {
    Write-Host "Criando ambiente Python..." -ForegroundColor Yellow
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Invoke-CheckedCommand -Command "py" -Arguments @("-3.11", "-m", "venv", ".venv") -WorkingDirectory $ProjectRoot
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-CheckedCommand -Command "python" -Arguments @("-m", "venv", ".venv") -WorkingDirectory $ProjectRoot
    }
    else {
        throw "Python 3.11 ou superior não foi encontrado. Instale Python e tente novamente."
    }

    Write-Host "Instalando dependências Python..." -ForegroundColor Yellow
    Invoke-CheckedCommand -Command $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -WorkingDirectory $ProjectRoot
    Invoke-CheckedCommand -Command $VenvPython -Arguments @("-m", "pip", "install", "-e", ".") -WorkingDirectory $ProjectRoot
}

Push-Location $ProjectRoot
try {
    & $VenvPython -c "import sys; sys.path.insert(0, 'src'); import certhub.web" 2>$null
    $PythonDependenciesReady = $LASTEXITCODE -eq 0
}
finally {
    Pop-Location
}
if (-not $PythonDependenciesReady) {
    Write-Host "Instalando/atualizando dependências Python..." -ForegroundColor Yellow
    Invoke-CheckedCommand -Command $VenvPython -Arguments @("-m", "pip", "install", "-e", ".") -WorkingDirectory $ProjectRoot
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm não foi encontrado. Instale a versão LTS do Node.js e tente novamente."
}

if (-not (Test-Path $FrontendModules)) {
    Write-Host "Instalando dependências do frontend..." -ForegroundColor Yellow
    if (Test-Path (Join-Path $FrontendDir "package-lock.json")) {
        Invoke-CheckedCommand -Command "npm" -Arguments @("ci") -WorkingDirectory $FrontendDir
    }
    else {
        Invoke-CheckedCommand -Command "npm" -Arguments @("install") -WorkingDirectory $FrontendDir
    }
}

Write-Host "Compilando o frontend..." -ForegroundColor Yellow
Invoke-CheckedCommand -Command "npm" -Arguments @("run", "build") -WorkingDirectory $FrontendDir

if (-not (Test-Path $FrontendDist)) {
    throw "A compilação terminou sem gerar frontend/dist. Verifique os erros acima."
}

Write-Host "Verificando/instalando Chromium do Playwright..." -ForegroundColor Yellow
Invoke-CheckedCommand -Command $VenvPython -Arguments @("-m", "playwright", "install", "chromium") -WorkingDirectory $ProjectRoot

Write-Host "Iniciando a API em $SiteUrl ..." -ForegroundColor Yellow
$Server = Start-Process -FilePath $VenvPython `
    -ArgumentList @("-m", "uvicorn", "certhub.web:app", "--app-dir", "src", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru

try {
    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        if ($Server.HasExited) {
            throw "A API encerrou antes de ficar disponível. Verifique se a porta 8000 está livre."
        }
        try {
            $Response = Invoke-WebRequest -Uri $SiteUrl -TimeoutSec 2 -UseBasicParsing
            if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
                $Ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) {
        throw "A API não respondeu em até 30 segundos."
    }

    Write-Host "Sistema pronto: $SiteUrl" -ForegroundColor Green
    Start-Process $SiteUrl
    Write-Host "Mantenha esta janela aberta; pressione Ctrl+C para encerrar o sistema." -ForegroundColor Green
    $Server.WaitForExit()
    if ($Server.ExitCode -ne 0) {
        throw "O servidor SIGi terminou com código $($Server.ExitCode)."
    }
}
finally {
    if (-not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force
    }
}
