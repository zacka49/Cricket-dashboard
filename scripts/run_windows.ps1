$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Candidates = @(
  @{ File = "py"; Args = @("-3") },
  @{ File = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"; Args = @() },
  @{ File = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"; Args = @() },
  @{ File = "python"; Args = @() }
)

$Python = $null
$PythonArgs = @()
foreach ($Candidate in $Candidates) {
  try {
    $Command = Get-Command $Candidate.File -ErrorAction Stop
    & $Command.Source @($Candidate.Args) -c "import httpx, pydantic, tenacity" | Out-Null
    $Python = $Command.Source
    $PythonArgs = $Candidate.Args
    break
  } catch {
    if (Test-Path -LiteralPath $Candidate.File) {
      try {
        & $Candidate.File @($Candidate.Args) -c "import httpx, pydantic, tenacity" | Out-Null
        $Python = $Candidate.File
        $PythonArgs = $Candidate.Args
        break
      } catch {
      }
    }
  }
}

if (-not $Python) {
  throw "Could not find a Python 3 interpreter with httpx, pydantic, and tenacity installed. Run: py -3 -m pip install -r requirements.txt"
}

Set-Location $ProjectRoot
& $Python @($PythonArgs) -m cricket_edge
