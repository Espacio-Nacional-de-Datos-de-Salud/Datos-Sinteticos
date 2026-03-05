# 1. Install uv if not found
if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "--- Installing uv ---" -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    $uvBin = "$env:USERPROFILE\.local\bin"
    if ($env:Path -notlike "*$uvBin*") {
        $env:Path = "$uvBin;$env:Path"
    }
}

# 2. Install Python 3.12.3
Write-Host "--- Ensuring Python 3.12.3 is installed ---" -ForegroundColor Cyan
uv python install 3.12.3

# 3. Create Core Environment (.venv_core)
Write-Host "--- Building Core Environment (.venv_core) ---" -ForegroundColor Cyan
uv venv .venv_core --python 3.12.3
uv pip install setuptools --python .venv_core\Scripts\python.exe
uv pip install -r requirements_core.txt --python .venv_core\Scripts\python.exe

# 4. Create Evaluation Environment (.venv_eval)
Write-Host "--- Building Evaluation Environment (.venv_eval) ---" -ForegroundColor Cyan
uv venv .venv_eval --python 3.12.3
uv pip install setuptools --python .venv_eval\Scripts\python.exe
uv pip install -r requirements_evaluation.txt --python .venv_eval\Scripts\python.exe

# 5. Apply Windows Timezone Patch (Mostly AI fix)
if ($IsWindows -or $env:OS -like "*Windows*") {
    Write-Host "--- Applying Windows Timezone Patch ---" -ForegroundColor Yellow
    $pythonPath = ".\.venv_core\Scripts\python.exe"
    
    # Usamos una ruta relativa directa al site-packages del venv
    $patchCommand = @"
import os
# Forzamos la ruta relativa al venv local
target = os.path.join('.venv_core', 'Lib', 'site-packages', 'mostlyai', 'sdk', '_data', 'dtype.py')

if os.path.exists(target):
    with open(target, 'r', encoding='utf-8') as f: 
        content = f.read()
    
    old = 'utc=True'
    new = 'utc=False'
    
    if old in content:
        with open(target, 'w', encoding='utf-8') as f: 
            f.write(content.replace(old, new))
        print('✅ Patch applied: Changed utc=True to utc=False in mostlyai SDK')
    else:
        # Verificamos si ya estaba aplicado para dar un mensaje claro
        if new in content:
            print('✔ Patch already present: utc=False is already set')
        else:
            print('⚠️ Patch skipped: target line not found in file')
else:
    print(f'❌ Patch failed: File not found at {os.path.abspath(target)}')
"@
    & $pythonPath -c $patchCommand
}

Write-Host "--- Setup Complete! ---" -ForegroundColor Green