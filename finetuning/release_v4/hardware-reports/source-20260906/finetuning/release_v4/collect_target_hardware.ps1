param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'hardware-reports')
)

# Read-only machine inventory. This does not load models or certify performance.
$ErrorActionPreference = 'Stop'
$issues = @()
$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$processors = @(Get-CimInstance Win32_Processor | ForEach-Object {
    [ordered]@{ name = $_.Name; cores = $_.NumberOfCores; logical_processors = $_.NumberOfLogicalProcessors }
})
$display = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [ordered]@{ name = $_.Name; driver_version = $_.DriverVersion }
})
$nvidia = @()
$smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($smi) {
    try {
        $lines = @(& $smi.Source '--query-gpu=name,memory.total,driver_version' '--format=csv,noheader,nounits' 2>$null)
        if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi returned a nonzero exit code' }
        $nvidia = @($lines | ConvertFrom-Csv -Header name,vram_mib,driver_version | ForEach-Object {
            [ordered]@{
                name = $_.name.Trim()
                vram_mib = [int]$_.vram_mib.Trim()
                driver_version = $_.driver_version.Trim()
            }
        })
    } catch { $issues += "NVIDIA inventory unavailable: $($_.Exception.Message)" }
} else {
    $issues += 'nvidia-smi unavailable; dedicated VRAM has not been verified.'
}

$localInference = [ordered]@{ version = $null; resident_models = @() }
try {
    $localInference.version = (Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3).version
    $resident = Invoke-RestMethod 'http://127.0.0.1:11434/api/ps' -TimeoutSec 3
    $localInference.resident_models = @($resident.models | Where-Object { $null -ne $_ } | ForEach-Object {
        [ordered]@{ name = $_.name; digest = $_.digest; size_bytes = $_.size; size_vram_bytes = $_.size_vram }
    })
} catch { $issues += 'Local inference service inventory unavailable; no model was started.' }

$gpuMatches = @($nvidia | Where-Object { $_.name -match 'RTX\s+4050' -and $_.vram_mib -ge 6000 -and $_.vram_mib -le 6200 }).Count -gt 0
$ramMatches = $computer.TotalPhysicalMemory -ge 23GB -and $computer.TotalPhysicalMemory -le 24.5GB
$report = [ordered]@{
    collected_utc = [DateTime]::UtcNow.ToString('o')
    expected = [ordered]@{ ram_gib = 24; gpu = 'RTX 4050'; dedicated_vram_gib = 6; os = 'Windows 11' }
    observed = [ordered]@{
        os = $os.Caption; os_version = $os.Version; os_build = $os.BuildNumber
        installed_ram_gib = [math]::Round($computer.TotalPhysicalMemory / 1GB, 3)
        available_ram_gib = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 3)
        processors = $processors
        display_adapters = $display; nvidia_gpus = $nvidia
        inference_service = $localInference
    }
    inventory_matches_target = ($os.Caption -match 'Windows 11' -and $ramMatches -and $gpuMatches)
    matching_policy = 'Windows 11; reported usable physical RAM 23–24.5 GiB (hardware reservation tolerance); RTX 4050 dedicated VRAM 6000–6200 MiB. Larger machines do not substitute for this target.'
    performance_tested = $false
    product_release_approved = $false
    issues = $issues
    scope = 'Inventory only. No model generation, UI input, downloads, installation, or cloud spending. No host name, serial number, user name, or network address collected.'
}
$destination = New-Item -ItemType Directory -Path $OutputDirectory -Force
$filename = 'hardware-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8) + '.json'
$reportPath = Join-Path $destination.FullName $filename
$json = $report | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText($reportPath, $json, (New-Object Text.UTF8Encoding($false)))
Write-Output $reportPath
