#requires -Version 5.1
<#
.SYNOPSIS
Collect local performance data for explicit process IDs into a new JSONL file.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateCount(1, 16)]
    [ValidateRange(1, 2147483647)]
    [int[]] $ProcessId,

    [Parameter(Mandatory = $true)]
    [string] $OutputPath,

    [ValidateRange(1, 300)]
    [int] $IntervalSeconds = 5,

    [ValidateRange(1, 86400)]
    [int] $DurationSeconds = 3600,

    [switch] $SystemDisk
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LocalOutputPath([string] $Path) {
    if ($Path.StartsWith('\\')) { throw 'Use a local filesystem path.' }
    $absolute = [IO.Path]::GetFullPath(
        [IO.Path]::Combine($ExecutionContext.SessionState.Path.CurrentFileSystemLocation.Path, $Path))
    $root = [IO.Path]::GetPathRoot($absolute)
    if ($root.StartsWith('\\') -or [IO.DriveInfo]::new($root).DriveType -eq [IO.DriveType]::Network) {
        throw 'Use a local filesystem path.'
    }
    if ($root -notmatch '^[a-z]:\\$' -or [IO.Path]::GetExtension($absolute) -ine '.jsonl') {
        throw 'Choose a new local .jsonl file.'
    }
    $parts = $absolute.Substring($root.Length).Split([IO.Path]::DirectorySeparatorChar)
    $componentPath = $root
    for ($i = 0; $i -lt $parts.Count; $i++) {
        $part = $parts[$i]
        if ($part.EndsWith(' ') -or $part.EndsWith('.') -or
            $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
            $part -match '^(CON|PRN|AUX|NUL|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])(?:\.|$)') {
            throw 'Choose a regular Windows filename.'
        }
        if ($i -lt $parts.Count - 1) {
            $componentPath = [IO.Path]::Combine($componentPath, $part)
            $parent = [IO.DirectoryInfo]::new($componentPath)
            if (-not $parent.Exists) { throw 'The output parent directory must exist.' }
            if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Use a path without reparse points.'
            }
        }
    }
    return $absolute
}

function Write-Record($Record) {
    $writer.WriteLine(($Record | ConvertTo-Json -Depth 6 -Compress))
}

function Get-OptionalCim([string] $Query) {
    try {
        Get-CimInstance -Query $Query -OperationTimeoutSec 2 -ErrorAction Stop
    }
    catch {
        # Missing providers, permissions, and transient counter failures are gaps.
    }
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This monitor requires Windows.'
}
if (@($ProcessId | Sort-Object -Unique).Count -ne $ProcessId.Count) {
    throw 'Each selected process ID must be unique.'
}

$absolutePath = Get-LocalOutputPath $OutputPath
$tracked = @{}
$stream = $null
$writer = $null
$clock = $null
$started = $false
$reason = 'interrupted'
try {
    $aliases = @()
    foreach ($id in $ProcessId) {
        $selected = [Diagnostics.Process]::GetProcessById($id)
        $tracked[$id] = $selected
        # Open and retain the process handle for the lifetime of the capture.
        # Stop if the selected process cannot be pinned or has already exited.
        $null = $selected.Handle
        if ($selected.HasExited) { throw 'A selected process exited before capture.' }
        $aliases += [ordered]@{
            id = $id
            name = $selected.ProcessName
            started_utc = $selected.StartTime.ToUniversalTime().ToString('o')
        }
    }

    $stream = [IO.FileStream]::new($absolutePath, [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    $clock = [Diagnostics.Stopwatch]::StartNew()
    Write-Record ([ordered]@{
        type = 'start'
        schema_version = 1
        timestamp_utc = [DateTime]::UtcNow.ToString('o')
        logical_processors = [Environment]::ProcessorCount
        interval_seconds = $IntervalSeconds
        duration_limit_seconds = $DurationSeconds
        system_disk_requested = [bool]$SystemDisk
        processes = $aliases
    })
    $started = $true
    while ($tracked.Count -gt 0 -and $clock.Elapsed.TotalSeconds -lt $DurationSeconds) {
        $tick = $clock.Elapsed.TotalSeconds
        $conditions = ($tracked.Keys | ForEach-Object { "ProcessId=$_" }) -join ' OR '
        $ioById = @{}
        foreach ($item in (Get-OptionalCim "SELECT ProcessId, ReadTransferCount, WriteTransferCount FROM Win32_Process WHERE $conditions")) {
            $ioById[[int]$item.ProcessId] = $item
        }
        $memory = Get-OptionalCim 'SELECT FreePhysicalMemory, TotalVisibleMemorySize FROM Win32_OperatingSystem'
        $freeBytes = $null
        $totalBytes = $null
        if ($null -ne $memory -and $null -ne $memory.FreePhysicalMemory -and $null -ne $memory.TotalVisibleMemorySize) {
            $freeBytes = [uint64]$memory.FreePhysicalMemory * 1024
            $totalBytes = [uint64]$memory.TotalVisibleMemorySize * 1024
        }
        $diskRead = $null
        $diskWrite = $null
        if ($SystemDisk) {
            $disk = Get-OptionalCim "SELECT DiskReadBytesPersec, DiskWriteBytesPersec FROM Win32_PerfFormattedData_PerfDisk_PhysicalDisk WHERE Name='_Total'"
            if ($null -ne $disk) {
                $diskRead = $disk.DiskReadBytesPersec
                $diskWrite = $disk.DiskWriteBytesPersec
            }
        }

        $elapsed = $clock.Elapsed.TotalSeconds
        $now = [DateTime]::UtcNow
        $records = @()
        foreach ($id in $ProcessId) {
            if (-not $tracked.ContainsKey($id)) { continue }
            $process = $tracked[$id]
            $record = [ordered]@{
                id = $id
                state = 'sampled'
                cpu_seconds = $null
                working_set_bytes = $null
                read_transfer_bytes = $null
                write_transfer_bytes = $null
                age_seconds = $null
            }
            try {
                $process.Refresh()
                if (-not $process.HasExited) {
                    $record.cpu_seconds = $process.TotalProcessorTime.TotalSeconds
                    $record.working_set_bytes = $process.WorkingSet64
                    $record.age_seconds = ($now - $process.StartTime.ToUniversalTime()).TotalSeconds
                    if ($ioById.ContainsKey($id)) {
                        $record.read_transfer_bytes = $ioById[$id].ReadTransferCount
                        $record.write_transfer_bytes = $ioById[$id].WriteTransferCount
                    }
                }
                else {
                    $record.state = 'exited'
                }
            }
            catch {
                $record.state = 'unavailable'
                try {
                    if ($process.HasExited) { $record.state = 'exited' }
                }
                catch {
                    # Retain the unavailable state.
                }
            }
            if ($record.state -ne 'sampled') {
                foreach ($key in @('cpu_seconds', 'working_set_bytes', 'read_transfer_bytes', 'write_transfer_bytes', 'age_seconds')) {
                    $record[$key] = $null
                }
            }
            if ($record.state -eq 'exited') {
                try {
                    $record.age_seconds = ($process.ExitTime - $process.StartTime).TotalSeconds
                }
                catch {
                    # Exit lifetime may be inaccessible.
                }
                $process.Dispose()
                $tracked.Remove($id)
            }
            $records += $record
        }
        Write-Record ([ordered]@{
            type = 'sample'
            timestamp_utc = $now.ToString('o')
            elapsed_seconds = $elapsed
            available_memory_bytes = $freeBytes
            total_memory_bytes = $totalBytes
            system_disk_read_bytes_per_second = $diskRead
            system_disk_write_bytes_per_second = $diskWrite
            processes = $records
        })
        if ($tracked.Count -gt 0) {
            $wait = [Math]::Min($tick + $IntervalSeconds, $DurationSeconds) - $clock.Elapsed.TotalSeconds
            if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]($wait * 1000)) }
        }
    }
    $reason = 'duration_limit'
    if ($tracked.Count -eq 0) { $reason = 'processes_exited' }
}
finally {
    try {
        if ($started) {
            Write-Record ([ordered]@{
                type = 'end'
                timestamp_utc = [DateTime]::UtcNow.ToString('o')
                elapsed_seconds = $clock.Elapsed.TotalSeconds
                reason = $reason
            })
        }
    }
    finally {
        if ($null -ne $writer) { $writer.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
        foreach ($process in $tracked.Values) { $process.Dispose() }
    }
}
