# Get the command (train, sim, or eval)
$cmd = $args[0]

# SAFE SLICING: Only grab remaining args if there are any
$remainingArgs = @()
if ($args.Count -gt 1) {
    $remainingArgs = $args[1..($args.Count - 1)]
}

# 1. HANDLE INTERACTIVE MODE (User just runs .\scripts\run.ps1)
if ([string]::IsNullOrWhiteSpace($cmd)) {
    Write-Host "--- Starting Interactive Assistant ---" -ForegroundColor Green
    & ".venv_core\Scripts\python.exe" -m src.main
    exit
}

# 2. HANDLE SCRIPT MODE (Mapping shorthand to actual Python flags)
switch ($cmd) {
    "t" {
        $venv = ".venv_core"
        $module = "src.main"
        $mode = "t"
    }
    "s" {
        $venv = ".venv_core"
        $module = "src.main"
        $mode = "s"
    }
    "e" {
        $venv = ".venv_eval"
        $module = "src.evaluation"
        $mode = $null
    }
    Default {
        Write-Host "Usage: .\scripts\run.ps1 {t|s|e}" -ForegroundColor Yellow
        Write-Host "Or run without arguments for the Interactive Assistant." -ForegroundColor Cyan
        exit
    }
}

$pythonPath = "$venv\Scripts\python.exe"

if (!(Test-Path $pythonPath)) {
    Write-Host "Error: Environment '$venv' not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit
}

Write-Host "--- Running $cmd mode ---" -ForegroundColor Cyan

if ($module -eq "src.main" -and $null -ne $mode) {
    $configPath = "config\execution_config.py"
    (Get-Content $configPath -Raw) -replace 'EXECUTION_MODE:\s*str\s*=\s*".*"', "EXECUTION_MODE: str = `"$mode`"" | Set-Content $configPath
    & $pythonPath -m $module
} else {
    & $pythonPath -m $module $remainingArgs
}
