param([string]$PazarAdi = "reklam-atolyesi")
$ErrorActionPreference = "Stop"
Set-StrictMode -Off
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$PluginAdi = "reklam-atolyesi"
function Update-YolDegiskeni {
    $parts = @()
    foreach ($scope in "Machine", "User") { $v = [Environment]::GetEnvironmentVariable("Path", $scope); if ($v) { $parts += $v.Split(";") } }
    $parts += $env:Path.Split(";")
    $seen = @{}; $out = @()
    foreach ($p in $parts) { $q = $p.Trim(); if ($q -and -not $seen.ContainsKey($q.ToLowerInvariant())) { $seen[$q.ToLowerInvariant()] = $true; $out += $q } }
    $env:Path = ($out -join ";")
}

function Find-Claude {
    foreach ($n in "claude.exe", "claude.cmd") { $c = Get-Command $n -ErrorAction SilentlyContinue; if ($c) { return $c.Source } }
    $native = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
    if (Test-Path $native) { return $native }
    $base = Join-Path $env:APPDATA "Claude\claude-code"
    if (Test-Path $base) {
        $cands = @(Get-ChildItem $base -Recurse -Depth 2 -Filter claude.exe -ErrorAction SilentlyContinue | Sort-Object FullName)
        if ($cands.Count -gt 0) { return $cands[-1].FullName }
    }
    return $null
}

function Get-ClaudeJson([string[]]$argv) {
    $out = @(& $script:ClaudeExe @argv)
    if ($LASTEXITCODE -ne 0) { return $null }
    # JSON, ilk '[' ya da '{' ile başlayan satırdan sonuna kadardır (önünde bilgi satırı olabilir).
    $start = -1
    for ($i = 0; $i -lt $out.Count; $i++) { if ("$($out[$i])".TrimStart().StartsWith("[") -or "$($out[$i])".TrimStart().StartsWith("{")) { $start = $i; break } }
    if ($start -lt 0) { return $null }
    try { $obj = (($out[$start..($out.Count - 1)]) -join "`n") | ConvertFrom-Json } catch { return $null }
    # Windows PowerShell 5.1 diziyi tek nesne olarak verir; öğelere açılır.
    return ,@($obj | ForEach-Object { $_ })
}

function Get-KuruluPlugin {
    $rows = Get-ClaudeJson @("plugin", "list", "--json")
    if ($null -eq $rows) { return $null }
    foreach ($r in $rows) { if ($r.id -eq "$PluginAdi@$PazarAdi") { return $r } }
    return $null
}

function Get-PluginAyarlari {
    $a = Get-ClaudeJson @("plugin", "configure", "$PluginAdi@$PazarAdi", "--json")
    if ($a -and $a.Count -gt 0) { return $a[0] }
    return $null
}

function Get-KayitliVeriKlasoru {
    # Plugin'e kurulumda verilen data_dir (hassas olmayan değer; claude plugin configure --json → inputs).
    $a = Get-PluginAyarlari
    if ($a -and $a.inputs -and $a.inputs.data_dir) { return [string]$a.inputs.data_dir }
    return $null
}

# Yalnızca mevcut kullanıcı kurulumunu günceller; kurulum/doctor/test çağırmaz.
function Invoke-Adim([string]$exe, [string[]]$argv) {
    $command = Get-Command $exe -ErrorAction Stop
    # Windows PowerShell 5.1, başarılı native programın stderr çıktısını da hata nesnesi yapar.
    $ErrorActionPreference = 'Continue'
    & $command.Source @argv 2>&1 | Out-Host
    $result = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($result -ne 0) { throw "Bir adım tamamlanamadı: $exe (hata kodu $result)" }
}
function Get-PythonKilit([string]$root) {
    return ((Get-Sha (Join-Path $root 'servers\ad_memory\uv.lock')) + ':' +
            (Get-Sha (Join-Path $root 'servers\ad_memory\pyproject.toml')))
}
function Get-Sha([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
}

$Gunluk = Join-Path $env:TEMP ('reklam-atolyesi-guncelleme-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$dd = $null
$code = 1
$updateLock = $null
try {
    Start-Transcript -Path $Gunluk | Out-Null
    Write-Host 'Reklam Atölyesi güncelleniyor.' -ForegroundColor Cyan
    Write-Host 'Başlamadan önce Claude uygulamasını ve açık Claude Code pencerelerini kapatın.'
    Update-YolDegiskeni
    $script:ClaudeExe = Find-Claude
    if (-not $script:ClaudeExe) { throw 'Bu bilgisayarda Claude Code bulunamadı. İlk kez kuruyorsanız kur.cmd dosyasını çalıştırın.' }
    $kurulu = Get-KuruluPlugin
    if (-not $kurulu -or $kurulu.scope -ne 'user' -or -not $kurulu.installPath) {
        throw 'Reklam Atölyesi bu bilgisayarda kurulu görünmüyor. İlk kez kuruyorsanız kur.cmd dosyasını çalıştırın.'
    }
    $dd = Get-KayitliVeriKlasoru
    if (-not $dd -or -not [IO.Path]::IsPathRooted($dd) -or -not (Test-Path -LiteralPath $dd -PathType Container)) {
        throw 'Reklam Atölyesi verilerinin durduğu klasör bulunamadı. Bu mesajı geliştiriciye iletin.'
    }
    $py = Join-Path $dd '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { throw 'Kurulumun bir parçası eksik görünüyor. Bu mesajı geliştiriciye iletin.' }
    # İkinci güncelleyicinin aynı veriye/bağımlılıklara eşzamanlı yazmasını engelle.
    $updateLock = [IO.File]::Open((Join-Path $dd '.guncelleme.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $env:PYTHONIOENCODING = 'utf-8'
    $helper = Join-Path $PSScriptRoot 'guncelle.py'
    $oldVersion = [string]$kurulu.version
    Write-Host "Şu an kurulu sürüm: $oldVersion"
    Invoke-Adim $py @($helper, 'backup', '--data-dir', $dd)
    $pythonStamp = Join-Path $dd '.guncelleme-python-sha256'
    if (-not (Test-Path -LiteralPath $pythonStamp)) {
        [IO.File]::WriteAllText($pythonStamp, (Get-PythonKilit $kurulu.installPath))
    }
    Invoke-Adim $script:ClaudeExe @('plugin', 'marketplace', 'update', $PazarAdi)
    Invoke-Adim $script:ClaudeExe @('plugin', 'update', "$PluginAdi@$PazarAdi", '--scope', 'user')
    $kurulu = Get-KuruluPlugin
    if (-not $kurulu -or -not $kurulu.installPath) { throw 'Yeni sürümün bilgisi okunamadı. Bu mesajı geliştiriciye iletin.' }
    $root = [string]$kurulu.installPath
    # Özellik bulunmadan başarı yazılmaz: yayımlanmamış/eski sürüme güncelleme anlaşılır biçimde durur.
    if (-not (Test-Path -LiteralPath (Join-Path $root 'hooks\error_notify.py'))) {
        throw 'Bu güncelleme dosyası, yayımlanan sürümle uyumlu değil. Geliştiricinin yeni sürümü yayımlaması gerekiyor.'
    }
    $want = Get-PythonKilit $root
    if ((Get-Content -LiteralPath $pythonStamp -Raw).Trim() -ne $want) {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Güncelleme için gereken bir program (uv) bulunamadı. kur.cmd dosyasını bir kez daha çalıştırın.' }
        Write-Host 'Gerekli program parçaları indiriliyor...'
        $env:UV_PROJECT_ENVIRONMENT = Join-Path $dd '.venv'
        $env:UV_LINK_MODE = 'copy'
        Invoke-Adim 'uv' @('sync', '--project', (Join-Path $root 'servers\ad_memory'), '--frozen', '--no-install-project', '--python', $py)
        [IO.File]::WriteAllText($pythonStamp, $want)
    } else { Write-Host 'Program parçaları zaten güncel.' }
    $nd = Join-Path $dd '.node'
    $tpl = Join-Path $root 'templates\remotion'
    $nodeStamp = Join-Path $nd '.kilit-sha256'
    $nodeHash = Get-Sha (Join-Path $tpl 'package-lock.json')
    $have = if (Test-Path -LiteralPath $nodeStamp) { (Get-Content -LiteralPath $nodeStamp -Raw).Trim() } else { '' }
    if ($have -ne $nodeHash -or -not (Test-Path -LiteralPath (Join-Path $nd 'node_modules\remotion'))) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Güncelleme için gereken bir program (npm) bulunamadı. kur.cmd dosyasını bir kez daha çalıştırın.' }
        Write-Host 'Video hazırlama parçaları indiriliyor...'
        New-Item -ItemType Directory -Force -Path $nd | Out-Null
        Copy-Item -LiteralPath (Join-Path $tpl 'package.json'), (Join-Path $tpl 'package-lock.json') -Destination $nd -Force
        Push-Location $nd
        try { Invoke-Adim 'npm.cmd' @('ci', '--no-audit', '--no-fund') } finally { Pop-Location }
        [IO.File]::WriteAllText($nodeStamp, $nodeHash)
    } else { Write-Host 'Video hazırlama parçaları zaten güncel.' }
    Invoke-Adim $py @($helper, 'finish', '--data-dir', $dd, '--plugin-root', $root, '--from-version', $oldVersion)
    Write-Host "GÜNCELLEME TAMAMLANDI. Yeni sürüm: $($kurulu.version)." -ForegroundColor Green
    Write-Host 'Şimdi Claude uygulamasını açın, yeni bir sohbet başlatın ve reklam-atolyesi yazın.'
    Write-Host 'Kullanırken bir hata olursa Reklam Atölyesi size hata defterini geliştiriciye göndermeyi önerir.'
    $code = 0
} catch {
    Write-Host "GÜNCELLEME TAMAMLANAMADI. Sebep: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Bu ekrandaki mesajı ve aşağıda yeri yazan kayıt dosyasını geliştiriciye gönderin.' -ForegroundColor Yellow
    Write-Host 'Güncelleme yarıda kalmış olabilir. Sorun çözülünce guncelle.cmd dosyasını yeniden çalıştırabilirsiniz; verileriniz yedeklendi.'
} finally {
    if ($updateLock) { $updateLock.Dispose() }
    Write-Host "Kayıt dosyası: $Gunluk"
    try { Stop-Transcript | Out-Null } catch { }
    if ($dd -and (Test-Path -LiteralPath $Gunluk)) {
        try {
            $logs = Join-Path $dd 'logs'
            New-Item -ItemType Directory -Force -Path $logs | Out-Null
            Copy-Item -LiteralPath $Gunluk -Destination $logs -Force
            Write-Host "Kayıt dosyasının kopyası: $(Join-Path $logs ([IO.Path]::GetFileName($Gunluk)))"
        } catch { Write-Host "Kayıt dosyası kopyalanamadı; yukarıda yeri yazan dosyayı gönderin." }
    }
}
exit $code
