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
    "train" {
        $venv = ".venv_core"
        $module = "src.main"
        # We explicitly map 'train' to '--mode train'
        $mappedArgs = @("--mode", "t")
    }
    "sim" {
        $venv = ".venv_core"
        $module = "src.main"
        # We explicitly map 'sim' to '--mode simulation'
        $mappedArgs = @("--mode", "s")
    }
    "eval" {
        $venv = ".venv_eval"
        $module = "src.eval"
        $mappedArgs = @()
    }
    Default {
        Write-Host "Usage: .\scripts\run.ps1 {train|sim|eval}" -ForegroundColor Yellow
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
# This executes: python -m src.main --mode train [other_args]
& $pythonPath -m $module $mappedArgs $remainingArgs
