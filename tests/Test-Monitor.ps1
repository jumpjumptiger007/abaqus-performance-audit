#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Run this test script on Windows.'
}

function Assert-True([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw $Message }
}

function Read-Capture([string] $Path) {
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object { ConvertFrom-Json $_ }
}

$monitor = Join-Path (Join-Path $PSScriptRoot '..') 'scripts\Monitor-Abaqus.ps1'
$directory = Join-Path ([IO.Path]::GetTempPath()) ('abaqus-audit-test-' + [Guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($directory)
$child = $null
try {
    # The disposable child exits on its own. The runner PID stays alive.
    $shell = (Get-Process -Id $PID).Path
    $child = Start-Process -FilePath $shell -ArgumentList '-NoProfile -NonInteractive -Command "Start-Sleep -Seconds 6"' -PassThru -WindowStyle Hidden
    $capture = Join-Path $directory 'exit.jsonl'
    & $monitor -ProcessId @($child.Id) -OutputPath $capture -IntervalSeconds 1 -DurationSeconds 20 -SystemDisk
    $records = @(Read-Capture $capture)
    Assert-True ($records[0].type -eq 'start') 'Capture start missing.'
    Assert-True ($records[0].processes[0].id -eq $child.Id) 'Unexpected PID in capture.'
    Assert-True ($records[-1].reason -eq 'processes_exited') 'Selected process exit did not finish capture.'
    $exits = @($records | Where-Object { $_.type -eq 'sample' -and $_.processes[0].state -eq 'exited' })
    Assert-True ($exits.Count -eq 1) 'Expected one exit observation.'

    $script:queries = @()
    function Get-CimInstance {
        [CmdletBinding()]
        param([string] $Query, [int] $OperationTimeoutSec)
        $script:queries += $Query
        throw 'Synthetic unavailable provider.'
    }

    $capture = Join-Path $directory 'missing.jsonl'
    & $monitor -ProcessId @($PID) -OutputPath $capture -IntervalSeconds 1 -DurationSeconds 2 -SystemDisk
    $records = @(Read-Capture $capture)
    $sample = $records[1]
    Assert-True ($sample.type -eq 'sample') 'Missing provider prevented sampling.'
    Assert-True ($null -ne $sample.processes[0].cpu_seconds) 'Expected a process CPU time sample.'
    Assert-True ($null -eq $sample.available_memory_bytes) 'Missing memory metric should be null.'
    Assert-True ($null -eq $sample.processes[0].read_transfer_bytes) 'Missing transfer metric should be null.'
    Assert-True ($null -eq $sample.system_disk_read_bytes_per_second) 'Missing disk metric should be null.'
    Assert-True ($records[-1].reason -eq 'duration_limit') 'Duration boundary was missed.'
    $processQueries = @($script:queries | Where-Object { $_ -match 'FROM Win32_Process' })
    Assert-True ($processQueries.Count -gt 0) 'Expected at least one scoped process query.'
    foreach ($query in $processQueries) {
        Assert-True ($query.EndsWith("WHERE ProcessId=$PID")) 'Process query scope changed.'
    }

    $before = [IO.File]::ReadAllText($capture)
    $rejected = $false
    try {
        & $monitor -ProcessId @($PID) -OutputPath $capture -IntervalSeconds 1 -DurationSeconds 1
    }
    catch {
        $rejected = $true
    }
    Assert-True ($rejected -and $before -ceq [IO.File]::ReadAllText($capture)) 'Existing capture was overwritten.'
    Write-Output 'Windows monitor integration checks passed.'
}
finally {
    if ($null -ne $child) { $child.Dispose() }
    # This test owns the GUID-named scratch directory and both files.
    [IO.Directory]::Delete($directory, $true)
}
