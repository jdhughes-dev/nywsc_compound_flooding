<#
.SYNOPSIS
    Sample CPU temperature, memory and disk to a CSV, one flushed row at a time.

.DESCRIPTION
    This laptop has hard-bugchecked five times under multi-hour coupled-model load
    (2026-07-13, 07-15, 07-30, 08-03, and 08-19 during run 6 of the start-phase
    matrix). Every one logs volmgr 161 "Dump file creation failed ...
    BugCheckProgress 0x00040049" and produces no dump at all -- no MEMORY.DMP, no
    minidump, no LiveKernelReports -- so there has never been a stop code to read.
    Two reboots after the 07-30 registry fix, C:\dedicateddump.sys was still never
    created; the dump stack cannot initialize on this storage path and there is no
    software lever left to pull.

    Which leaves evidence gathered before the fact. Every row is appended the moment
    it is taken, on the same reasoning as run_scenario.py's Tee: a machine that dies
    without warning still leaves a file saying what the run looked like just before.
    What the tail of the CSV shows is the whole point --

      temperature climbing into the crash   -> thermal, and the fix is airflow
      available memory falling to nothing   -> the run, not the hardware
      disk queue or latency spiking         -> the storage path, which is where the
                                               failed dump writes and the WHEA
                                               cache-hierarchy errors already point
      all three flat                        -> none of the above, and MemTest86 is
                                               the only question left worth asking

    Three columns carry the suspects, so all three are logged at full rate.

    CPU temperature is the ACPI thermal zone, read as tenths of a kelvin from the
    HighPrecisionTemperature counter. It needs no elevation, unlike
    MSAcpi_ThermalZoneTemperature, which returns Access denied here. NVMe drive
    temperature would be the single most interesting number given where the failure
    is, but Get-StorageReliabilityCounter does need an administrator token: run with
    -IncludeDisk from an elevated shell to fill the nvme_c column.

    D-Flow FM has no process of its own -- the notebook drives it through its DLL --
    so the python.exe working set is the coupled model's memory, MODFLOW and SWMM
    included.

.PARAMETER IntervalSeconds
    Seconds between samples, 600 by default. Worth knowing what that costs: the row
    that matters is the last one before the machine goes down, so a ten-minute
    cadence can leave the crash up to ten minutes past the final sample and miss a
    ramp entirely. The sampling itself is three CIM queries and is free at any
    cadence -- pass -IntervalSeconds 15 if the next crash should be caught closely.

.PARAMETER FootprintMinutes
    How often to add up what the start-phase matrix is holding on disk. This one
    walks the run directories, so it is deliberately slower than the counters; the
    number moves in gigabyte steps as runs land, not in seconds. Zero disables it.

.PARAMETER Summary
    Read the CSV back instead of sampling: temperature, memory and disk extremes,
    time spent throttled, and the last row before the log stops -- which after a
    crash is the row the whole file exists for.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\monitor_thermals.ps1
    powershell -ExecutionPolicy Bypass -File tools\monitor_thermals.ps1 -Summary
#>
[CmdletBinding()]
param(
    [double]$IntervalSeconds = 600,
    [double]$FootprintMinutes = 10,
    [string]$Csv,
    [switch]$Summary,
    [switch]$IncludeDisk,
    [double]$WarnC = 90,
    [double]$WarnAvailMB = 2048
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Csv) { $Csv = Join-Path $root 'logs\thermals.csv' }
$logDir = Join-Path $root 'logs'

# The i7-8665U nominal clock, which PercentProcessorPerformance is a percentage of.
# The ProcessorFrequency counter alone does not track the real clock on this part.
$NOMINAL_MHZ = 1900

$COLUMNS = 'time,temp_c,throttle,passive_pct,cpu_pct,cpu_mhz,' +
           'mem_avail_mb,mem_commit_pct,mem_pages_sec,model_rss_mb,' +
           'disk_free_gb,disk_queue,disk_pct_time,disk_read_mbs,disk_write_mbs,' +
           'nvme_c,run_gb,scenario'

# Where the start-phase matrix puts its weight. results/ is what the archive is
# built from; the other two hold the working directories nothing downstream reads.
$FOOTPRINT = @(
    (Join-Path $root 'results\gp'),
    (Join-Path $root 'dflow-fm\coarse'),
    (Join-Path $root 'modflow\gp_chd')
)

function Get-Footprint {
    $sum = 0
    foreach ($base in $FOOTPRINT) {
        if (-not (Test-Path $base)) { continue }
        # Tagged scenarios only. The untagged production runs are not this
        # experiment's footprint and would swamp the number they were added to.
        $dirs = Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '_t\d{4}$' }
        foreach ($d in $dirs) {
            $m = Get-ChildItem $d.FullName -Recurse -File -ErrorAction SilentlyContinue |
                 Measure-Object -Property Length -Sum
            if ($m.Sum) { $sum += $m.Sum }
        }
    }
    return [math]::Round($sum / 1GB, 2)
}

function Get-Sample {
    param([string]$RunGb)
    $r = [ordered]@{
        time = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        temp_c = ''; throttle = ''; passive_pct = ''; cpu_pct = ''; cpu_mhz = ''
        mem_avail_mb = ''; mem_commit_pct = ''; mem_pages_sec = ''; model_rss_mb = ''
        disk_free_gb = ''; disk_queue = ''; disk_pct_time = ''
        disk_read_mbs = ''; disk_write_mbs = ''; nvme_c = ''
        run_gb = $RunGb; scenario = ''
    }
    # The hottest zone, not the first: a machine reporting several would otherwise
    # be summarised by whichever one happened to enumerate last.
    try {
        $tz = Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation -ErrorAction Stop |
              Sort-Object HighPrecisionTemperature -Descending | Select-Object -First 1
        if ($tz) {
            $r.temp_c      = [math]::Round($tz.HighPrecisionTemperature / 10.0 - 273.15, 2)
            $r.throttle    = $tz.ThrottleReasons
            $r.passive_pct = $tz.PercentPassiveLimit
        }
    } catch { }
    try {
        $c = Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation -ErrorAction Stop |
             Where-Object { $_.Name -eq '_Total' } | Select-Object -First 1
        if ($c) {
            $r.cpu_pct = $c.PercentProcessorTime
            $r.cpu_mhz = [math]::Round($NOMINAL_MHZ * $c.PercentProcessorPerformance / 100.0)
        }
    } catch { }
    try {
        $m = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction Stop
        $r.mem_avail_mb   = $m.AvailableMBytes
        $r.mem_commit_pct = $m.PercentCommittedBytesInUse
        # Hard faults per second. A run that starts paging is a run about to be
        # slower than the timings assume, and that is worth seeing before the fact.
        $r.mem_pages_sec  = $m.PagesPerSec
    } catch { }
    try {
        $p = @(Get-Process -Name python -ErrorAction SilentlyContinue)
        if ($p.Count -gt 0) {
            $r.model_rss_mb = [math]::Round((($p | Measure-Object -Property WorkingSet64 -Sum).Sum) / 1MB)
        }
    } catch { }
    try { $r.disk_free_gb = [math]::Round((Get-PSDrive C -ErrorAction Stop).Free / 1GB, 1) } catch { }
    try {
        $d = Get-CimInstance Win32_PerfFormattedData_PerfDisk_LogicalDisk -ErrorAction Stop |
             Where-Object { $_.Name -eq '_Total' } | Select-Object -First 1
        if ($d) {
            $r.disk_queue     = $d.AvgDiskQueueLength
            $r.disk_pct_time  = $d.PercentDiskTime
            $r.disk_read_mbs  = [math]::Round($d.DiskReadBytesPerSec / 1MB, 1)
            $r.disk_write_mbs = [math]::Round($d.DiskWriteBytesPerSec / 1MB, 1)
        }
    } catch { }
    if ($IncludeDisk) {
        try {
            $s = Get-PhysicalDisk -ErrorAction Stop | Get-StorageReliabilityCounter -ErrorAction Stop |
                 Sort-Object Temperature -Descending | Select-Object -First 1
            if ($s) { $r.nvme_c = $s.Temperature }
        } catch { }
    }
    # Which run was in flight, so a number can be tied to a scenario after the fact.
    # run_scenario.py writes every few seconds, so a log touched inside three
    # minutes is the live one.
    try {
        $l = Get-ChildItem (Join-Path $logDir 'gp_*.log') -ErrorAction Stop |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($l -and ((Get-Date) - $l.LastWriteTime).TotalMinutes -lt 3) { $r.scenario = $l.BaseName }
    } catch { }
    return [pscustomobject]$r
}

function Show-Stat {
    param([array]$Rows, [string]$Col, [string]$Label, [string]$Unit)
    $v = @($Rows | Where-Object { $_.$Col -ne '' } | ForEach-Object { [double]$_.$Col })
    if ($v.Count -eq 0) { return }
    $s = $v | Measure-Object -Maximum -Minimum -Average
    Write-Output ("  {0,-15} max {1,9:n1}   mean {2,9:n1}   min {3,9:n1}  {4}" -f $Label, $s.Maximum, $s.Average, $s.Minimum, $Unit)
}

function Show-Summary {
    if (-not (Test-Path $Csv)) { Write-Output "no log at $Csv"; return }
    $rows = @(Import-Csv $Csv)
    if ($rows.Count -eq 0) { Write-Output "no samples in $Csv"; return }
    $span = [datetime]$rows[-1].time - [datetime]$rows[0].time
    Write-Output $Csv
    Write-Output ("  {0} samples over {1:n1} h, {2} -> {3}" -f $rows.Count, $span.TotalHours, $rows[0].time, $rows[-1].time)
    Show-Stat $rows 'temp_c'       'cpu temp'       'C'
    Show-Stat $rows 'cpu_mhz'      'cpu clock'      'MHz'
    Show-Stat $rows 'mem_avail_mb' 'memory free'    'MB'
    Show-Stat $rows 'model_rss_mb' 'model rss'      'MB'
    Show-Stat $rows 'disk_free_gb' 'disk free'      'GB'
    Show-Stat $rows 'disk_queue'   'disk queue'     ''
    Show-Stat $rows 'run_gb'       'matrix on disk' 'GB'
    $hot   = @($rows | Where-Object { $_.temp_c -ne '' -and [double]$_.temp_c -ge $WarnC })
    $thr   = @($rows | Where-Object { $_.throttle -ne '' -and [int]$_.throttle -ne 0 })
    $tight = @($rows | Where-Object { $_.mem_avail_mb -ne '' -and [double]$_.mem_avail_mb -le $WarnAvailMB })
    Write-Output ("  at or above {0} C: {1} samples; throttled: {2}; memory under {3} MB: {4}" -f $WarnC, $hot.Count, $thr.Count, $WarnAvailMB, $tight.Count)
    $l = $rows[-1]
    Write-Output "  last row before the log stops -- after a crash, the row this file exists for:"
    Write-Output ("    {0}  {1} C  cpu {2} pct at {3} MHz  free mem {4} MB  disk q {5}  {6}" -f $l.time, $l.temp_c, $l.cpu_pct, $l.cpu_mhz, $l.mem_avail_mb, $l.disk_queue, $l.scenario)
}

if ($Summary) { Show-Summary; return }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Csv) | Out-Null
if (-not (Test-Path $Csv)) { Add-Content -Path $Csv -Encoding utf8 -Value $COLUMNS }

Write-Output "logging every $IntervalSeconds s to $Csv  (Ctrl-C to stop)"
$runGb = ''
$nextFootprint = Get-Date
while ($true) {
    if ($FootprintMinutes -gt 0 -and (Get-Date) -ge $nextFootprint) {
        $runGb = Get-Footprint
        $nextFootprint = (Get-Date).AddMinutes($FootprintMinutes)
    }
    $s = Get-Sample -RunGb $runGb
    $line = '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14},{15},{16},{17}' -f
        $s.time, $s.temp_c, $s.throttle, $s.passive_pct, $s.cpu_pct, $s.cpu_mhz,
        $s.mem_avail_mb, $s.mem_commit_pct, $s.mem_pages_sec, $s.model_rss_mb,
        $s.disk_free_gb, $s.disk_queue, $s.disk_pct_time, $s.disk_read_mbs,
        $s.disk_write_mbs, $s.nvme_c, $s.run_gb, $s.scenario
    # Appended per sample, never buffered: the point is the row written one tick
    # before the machine goes down.
    Add-Content -Path $Csv -Encoding utf8 -Value $line
    $flag = ''
    if ($s.temp_c -ne '' -and [double]$s.temp_c -ge $WarnC) { $flag = $flag + '  ** hot' }
    if ($s.throttle -ne '' -and [int]$s.throttle -ne 0) { $flag = $flag + '  ** throttled' }
    if ($s.mem_avail_mb -ne '' -and [double]$s.mem_avail_mb -le $WarnAvailMB) { $flag = $flag + '  ** memory low' }
    Write-Output ("{0}  {1,5} C  cpu {2,3} pct {3,4} MHz  mem {4,6} MB free / rss {5,5} MB  disk {6,5} GB free q{7}{8}" -f
        $s.time, $s.temp_c, $s.cpu_pct, $s.cpu_mhz, $s.mem_avail_mb, $s.model_rss_mb, $s.disk_free_gb, $s.disk_queue, $flag)
    Start-Sleep -Seconds $IntervalSeconds
}
