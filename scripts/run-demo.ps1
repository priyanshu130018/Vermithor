# Vermithor Interactive Demo Runner for Windows PowerShell
# Usage:
#   .\scripts\run-demo.ps1 [database | deployment | redis | memory | traffic | auth | ambiguous | all]

param (
    [string]$Scenario = "database",
    [string]$ApiUrl = "http://localhost:8080"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Vermithor Interactive Demo Runner (Windows)" -ForegroundColor Cyan
Write-Host " Scenario: $Scenario" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

python scripts/demo/synthetic-incidents/generator.py "$Scenario" --api-url "$ApiUrl"
