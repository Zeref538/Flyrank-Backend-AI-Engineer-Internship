<#
Runs every checkpoint of the "Containerize your stack" brief and prints PASS or FAIL.

    powershell -ExecutionPolicy Bypass -File .\verify-docker.ps1

It uses its own compose project name, "a3check", so it gets its own database
volume: it never touches your real data, and at the end it deletes only its own.

    .\verify-docker.ps1 -ApiOnly -BaseUrl http://localhost:3000

runs just the HTTP checks against an API that is already running (no Docker).
#>
param(
    [switch]$ApiOnly,
    [string]$BaseUrl = "http://localhost:3000"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$script:failed = 0
$project = "a3check"

function Check([string]$name, [bool]$ok, [string]$detail = "") {
    if ($ok) { Write-Host "PASS  $name" -ForegroundColor Green }
    else { Write-Host "FAIL  $name  $detail" -ForegroundColor Red; $script:failed++ }
}

# HttpClient instead of Invoke-WebRequest: in Windows PowerShell 5.1,
# Invoke-WebRequest throws on every 4xx, and 400/404 are answers we want to read.
Add-Type -AssemblyName System.Net.Http
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromSeconds(30)

function Call([string]$method, [string]$path, [string]$json = $null) {
    $req = New-Object System.Net.Http.HttpRequestMessage ([System.Net.Http.HttpMethod]::new($method)), ($BaseUrl + $path)
    if ($json) { $req.Content = New-Object System.Net.Http.StringContent $json, ([Text.Encoding]::UTF8), "application/json" }
    $res = $http.SendAsync($req).GetAwaiter().GetResult()
    $text = $res.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $body = $null
    if ($text) { try { $body = $text | ConvertFrom-Json } catch { $body = $text } }
    return @{ code = [int]$res.StatusCode; body = $body; text = $text }
}

function Test-Api {
    $h = Call GET "/health"
    Check "GET /health says the database answers" ($h.code -eq 200 -and $h.body.db -eq "ok") "got $($h.code) $($h.text)"

    $all = Call GET "/tasks"
    Check "GET /tasks is 200 with the seeded tasks" ($all.code -eq 200 -and @($all.body).Count -ge 3) "got $($all.code), $(@($all.body).Count) rows"

    $made = Call POST "/tasks" '{"title":"Survive a restart"}'
    Check "POST /tasks is 201 and returns the new id" ($made.code -eq 201 -and $made.body.id) "got $($made.code) $($made.text)"
    $id = $made.body.id

    $put = Call PUT "/tasks/$id" '{"done":true}'
    Check "PUT /tasks/$id is 200 and marks it done" ($put.code -eq 200 -and $put.body.done -eq $true) "got $($put.code) $($put.text)"

    $bad = Call POST "/tasks" '{}'
    Check "POST with no title is 400 with a JSON error" ($bad.code -eq 400 -and $bad.body.error) "got $($bad.code) $($bad.text)"

    $none = Call GET "/tasks/999999"
    Check "GET an unknown id is 404 with a JSON error" ($none.code -eq 404 -and $none.body.error) "got $($none.code) $($none.text)"

    $doomed = Call POST "/tasks" '{"title":"Delete me"}'
    $del = Call DELETE "/tasks/$($doomed.body.id)"
    Check "DELETE is 204 with an empty body" ($del.code -eq 204 -and -not $del.text) "got $($del.code) '$($del.text)'"
    $gone = Call GET "/tasks/$($doomed.body.id)"
    Check "the deleted task is really gone (404)" ($del.code -eq 204 -and $gone.code -eq 404) "delete $($del.code), get $($gone.code)"

    return $id
}

if ($ApiOnly) {
    [void](Test-Api)
    if ($script:failed) { Write-Host "`n$script:failed check(s) failed" -ForegroundColor Red; exit 1 }
    Write-Host "`nall API checks passed" -ForegroundColor Green; exit 0
}

# --- Docker is installed and its engine is actually running -------------------
$dockerOk = $false
try { docker info --format "{{.ServerVersion}}" *> $null; $dockerOk = ($LASTEXITCODE -eq 0) } catch {}
if (-not $dockerOk) {
    Write-Host "Docker is not running. Start Docker Desktop and wait for the whale icon to stop moving, then re-run." -ForegroundColor Yellow
    exit 1
}
Check "Docker engine is running" $true

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "      made .env from .env.example (the brief's: cp .env.example .env)"
}
$busy = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if ($busy) { Write-Host "Port 3000 is already in use by another program. Stop it, then re-run." -ForegroundColor Yellow; exit 1 }

try {
    # --wait returns only once the healthchecks pass: the db answers pg_isready
    docker compose -p $project up -d --build --wait
    Check "docker compose up starts api and db, healthy" ($LASTEXITCODE -eq 0)
    $id = Test-Api

    Write-Host "      restarting the whole stack: down, then up"
    docker compose -p $project down
    docker compose -p $project up -d --wait
    $after = Call GET "/tasks/$id"
    Check "task $id survived docker compose down + up (the volume kept it)" ($after.code -eq 200 -and $after.body.title -eq "Survive a restart") "got $($after.code) $($after.text)"

    # The brief's screenshot: psql \dt and a SELECT, from inside the container.
    $psql = docker compose -p $project exec -T db psql -U postgres -d tasks -c "\dt" -c "SELECT * FROM tasks ORDER BY id;" 2>&1
    $psql | Out-File -Encoding utf8 docs\psql-session.txt
    Check "psql inside the db container lists the tasks table" ([bool]($psql -match "tasks")) ($psql -join " ")
    Write-Host ""; $psql | ForEach-Object { Write-Host "      $_" }; Write-Host "      (saved to docs\psql-session.txt)"
}
finally {
    # Remove only this check's containers and its own volume, never yours.
    docker compose -p $project down -v *> $null
}

if ($script:failed) { Write-Host "`n$script:failed check(s) failed" -ForegroundColor Red; exit 1 }
Write-Host "`nevery A3 checkpoint passed" -ForegroundColor Green
