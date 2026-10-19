[CmdletBinding()]
param([switch]$Incremental)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$captureRoot = Join-Path $projectRoot 'data/outputs/captures'
$backupRoot = 'C:\Users\USER\VisionInsight_GrabBackup_Step11_20261019'
$expected = @{
    'CAP-0e821e45b4d04984ad7f56f3dd3decf8.png' = '4bbff87d5eae08d9b9b31e873bfc6275b10a4b2b6149cbb6804d9632f775955f'
    'CAP-14543e2caf6d4ee58ad1fdd91bd6ff14.png' = 'bda88e853d4a28093441317eebf6ec8393652e7125957599a1e41bcd53310d09'
    'CAP-411dbfc718be42ef91885ca243ecb465.png' = 'cf948eebae9fe8c865a3e25fb19570fcb2ab4faf03d9d9bdfd570c59b78bc363'
    'CAP-db609379922a4b4e883cd894931923e1.png' = 'e5a0d231486bae29eb5c660e45acbddb78c99e6e5f87c0c5f13e57945b9db044'
}
if ($Incremental) {
    $backupRoot = 'C:\Users\USER\VisionInsight_GrabBackup_Step11_20261019_Incremental_01'
    $expected = @{
        'CAP-c6a86173515b4005b0c7c485df30f49a.png' = 'f1332dcec2ffd1e06822385a31897f4fd2aaee69bb86d766243aa668f2f565e9'
    }
}
$held = [System.Collections.Generic.List[object]]::new()
$subscriptions = [System.Collections.Generic.List[string]]::new()
$watcher = $null
$created = $false

function Get-StreamHash($stream) {
    $stream.Position = 0
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Position = 0 }
}

function Get-ExistingFingerprints {
    $paths = @((Join-Path $projectRoot 'data/inspections.jsonl'), (Join-Path $projectRoot 'data/inspection_logs.jsonl'))
    $directories = @('C:\Users\USER\VisionInsight_GrabBackup_20261018', 'C:\Users\USER\VisionInsight_GrabBackup_Step9_20261018')
    if ($Incremental) { $directories += 'C:\Users\USER\VisionInsight_GrabBackup_Step11_20261019' }
    foreach ($directory in $directories) {
        $paths += @(Get-ChildItem -LiteralPath $directory -File | ForEach-Object { $_.FullName })
    }
    $fingerprints = @{}
    foreach ($path in $paths) { $fingerprints[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
    return $fingerprints
}

function Assert-SourceSet {
    $names = @(Get-ChildItem -LiteralPath $captureRoot -File -Filter '*.png' | ForEach-Object { $_.Name })
    if ($names.Count -ne $expected.Count -or @(Compare-Object @($expected.Keys | Sort-Object) @($names | Sort-Object)).Count) {
        throw 'SOURCE_PNG_SET_CHANGED'
    }
}

function Assert-NoChangeEvents {
    foreach ($identifier in $subscriptions) {
        if (@(Get-Event -SourceIdentifier $identifier -ErrorAction SilentlyContinue).Count) { throw 'SOURCE_CHANGE_OR_WATCHER_ERROR_OBSERVED' }
    }
}

function Write-NewJson($path, $value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($value | ConvertTo-Json -Depth 12))
    $target = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $target.Write($bytes, 0, $bytes.Length); $target.Flush($true) }
    finally { $target.Dispose() }
}

try {
    if (Test-Path -LiteralPath $backupRoot) { throw 'BACKUP_DIRECTORY_ALREADY_EXISTS' }
    $startedAt = [DateTime]::UtcNow.ToString('o')
    $watcher = [IO.FileSystemWatcher]::new($captureRoot, '*.png')
    $watcher.NotifyFilter = [IO.NotifyFilters]::FileName -bor [IO.NotifyFilters]::Size -bor [IO.NotifyFilters]::LastWrite
    $watcher.InternalBufferSize = 65536
    foreach ($eventName in @('Created', 'Changed', 'Deleted', 'Renamed', 'Error')) {
        $identifier = 'step11-capture-backup-' + [guid]::NewGuid().ToString('N')
        Register-ObjectEvent -InputObject $watcher -EventName $eventName -SourceIdentifier $identifier | Out-Null
        $subscriptions.Add($identifier)
    }
    $watcher.EnableRaisingEvents = $true
    Assert-SourceSet
    $before = Get-ExistingFingerprints
    foreach ($name in @($expected.Keys | Sort-Object)) {
        $sourcePath = Join-Path $captureRoot $name
        $item = Get-Item -LiteralPath $sourcePath
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'SOURCE_LINK_REJECTED' }
        $source = [IO.File]::Open($sourcePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $entry = [pscustomobject]@{ filename = $name; capture_id = [IO.Path]::GetFileNameWithoutExtension($name);
            source_path = $sourcePath; backup_path = (Join-Path $backupRoot $name); bytes = $source.Length;
            source_last_write_utc = $item.LastWriteTimeUtc.ToString('o'); source_sha256_before = (Get-StreamHash $source);
            related_inspections = @(); stream = $source }
        $held.Add($entry)
        if ($entry.source_sha256_before -ne $expected[$name]) { throw 'SOURCE_HASH_CHANGED_SINCE_APPROVAL' }
    }
    foreach ($line in [IO.File]::ReadLines((Join-Path $projectRoot 'data/inspections.jsonl'))) {
        $record = $line | ConvertFrom-Json
        $provenance = $record.metrics.input_provenance
        if ($provenance -and $provenance.capture_id) {
            foreach ($entry in $held) {
                if ($provenance.capture_id -eq $entry.capture_id) {
                    $entry.related_inspections += [pscustomobject]@{ inspection_id = $record.inspection_id;
                        video_id = $provenance.video_id; frame_index = $provenance.frame_index; roi = $provenance.roi;
                        crop_width = $provenance.crop_width; crop_height = $provenance.crop_height }
                }
            }
        }
    }
    Assert-NoChangeEvents
    Assert-SourceSet
    New-Item -ItemType Directory -Path $backupRoot -ErrorAction Stop | Out-Null
    $created = $true
    $verifiedFiles = @()
    foreach ($entry in $held) {
        $entry.stream.Position = 0
        $destination = [IO.File]::Open($entry.backup_path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $entry.stream.CopyTo($destination); $destination.Flush($true) }
        finally { $destination.Dispose() }
        $sourceAfter = Get-StreamHash $entry.stream
        $backupHash = (Get-FileHash -LiteralPath $entry.backup_path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sourceAfter -ne $entry.source_sha256_before -or $backupHash -ne $entry.source_sha256_before) { throw 'TRIPLE_HASH_MISMATCH' }
        $verifiedFiles += [pscustomobject]@{ filename = $entry.filename; capture_id = $entry.capture_id;
            source_path = $entry.source_path; backup_path = $entry.backup_path; bytes = $entry.bytes;
            source_last_write_utc = $entry.source_last_write_utc; source_sha256_before = $entry.source_sha256_before;
            source_sha256_after = $sourceAfter; backup_sha256 = $backupHash; verification_status = 'PASS';
            related_inspections = $entry.related_inspections;
            metadata_status = $(if ($entry.related_inspections.Count) { 'EXISTING_INSPECTION_PROVENANCE' } else { 'UNKNOWN_NO_MATCHING_INSPECTION_PROVENANCE' }) }
        Assert-NoChangeEvents
    }
    Assert-SourceSet
    $after = Get-ExistingFingerprints
    if ($before.Count -ne $after.Count) { throw 'EXISTING_ASSET_SET_CHANGED' }
    foreach ($path in $before.Keys) { if ($before[$path] -ne $after[$path]) { throw 'EXISTING_ASSET_CHANGED' } }
    Assert-NoChangeEvents
    $manifest = [pscustomobject]@{ schema_version = 1; started_at_utc = $startedAt; verified_at_utc = [DateTime]::UtcNow.ToString('o');
        verification_status = 'VERIFIED'; png_count = $verifiedFiles.Count; source_change_observed = $false;
        verification = 'SOURCE_BEFORE_EQUALS_SOURCE_AFTER_EQUALS_BACKUP_SHA256';
        source_protection = 'Read-only streams deny concurrent write/delete during copy; PNG change watcher and repeated source-set checks';
        existing_asset_fingerprints_before = $before; existing_asset_fingerprints_after = $after;
        metadata_scope = 'Allowlisted inspection provenance only; no session tokens, credentials, prompts or ground truth';
        restore_scope = 'PNG bytes only; CaptureStore memory sessions and registrations are not restored'; files = $verifiedFiles }
    Write-NewJson (Join-Path $backupRoot 'backup_manifest.json') $manifest
    $reread = Get-Content -LiteralPath (Join-Path $backupRoot 'backup_manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($reread.png_count -ne $expected.Count -or $reread.verification_status -ne 'VERIFIED') { throw 'MANIFEST_VALIDATION_FAILED' }
    if (@(Get-ChildItem -LiteralPath $backupRoot -File).Count -ne ($expected.Count + 1)) { throw 'UNEXPECTED_BACKUP_FILE' }
    Assert-SourceSet
    Assert-NoChangeEvents
    [pscustomobject]@{ status = 'PASS'; png_count = $expected.Count; manifest_path = (Join-Path $backupRoot 'backup_manifest.json');
        source_change_observed = $false; existing_assets_unchanged = $true; files = $verifiedFiles } | ConvertTo-Json -Depth 9
} catch {
    if ($created -and -not (Test-Path -LiteralPath (Join-Path $backupRoot 'backup_failure.json'))) {
        try { Write-NewJson (Join-Path $backupRoot 'backup_failure.json') ([pscustomobject]@{ status = 'INCOMPLETE';
            failed_at_utc = [DateTime]::UtcNow.ToString('o'); reason = $_.Exception.Message }) } catch { }
    }
    Write-Error $_
    exit 1
} finally {
    foreach ($entry in $held) { $entry.stream.Dispose() }
    if ($watcher) { $watcher.EnableRaisingEvents = $false }
    foreach ($identifier in $subscriptions) {
        Unregister-Event -SourceIdentifier $identifier -ErrorAction SilentlyContinue
        Get-Event -SourceIdentifier $identifier -ErrorAction SilentlyContinue | Remove-Event -ErrorAction SilentlyContinue
    }
    if ($watcher) { $watcher.Dispose() }
}
