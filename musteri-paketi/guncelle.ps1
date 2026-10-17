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
    if ($result -ne 0) { throw "İşlem başarısız: $exe (çıkış kodu $result)" }
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
    Write-Host 'Reklam Atölyesi — güncelleme (test çalıştırılmaz)' -ForegroundColor Cyan
    Write-Host 'Başlamadan önce Claude masaüstü uygulamasını ve açık Claude Code oturumlarını kapatın.'
    Update-YolDegiskeni
    $script:ClaudeExe = Find-Claude
    if (-not $script:ClaudeExe) { throw 'Claude Code bulunamadı. İlk kurulum için kur.cmd kullanın.' }
    $kurulu = Get-KuruluPlugin
    if (-not $kurulu -or $kurulu.scope -ne 'user' -or -not $kurulu.installPath) {
        throw 'Kullanıcı kapsamında mevcut kurulum bulunamadı. İlk kurulum için kur.cmd kullanın.'
    }
    $dd = Get-KayitliVeriKlasoru
    if (-not $dd -or -not [IO.Path]::IsPathRooted($dd) -or -not (Test-Path -LiteralPath $dd -PathType Container)) {
        throw 'Kayıtlı veri klasörü okunamadı. Claude plugin ayarındaki data_dir değerini kontrol edin.'
    }
    $py = Join-Path $dd '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { throw 'Mevcut Python ortamı bulunamadı. Sağlayıcınızdan destek isteyin.' }
    # İkinci güncelleyicinin aynı veriye/bağımlılıklara eşzamanlı yazmasını engelle.
    $updateLock = [IO.File]::Open((Join-Path $dd '.guncelleme.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $env:PYTHONIOENCODING = 'utf-8'
    $helper = Join-Path $PSScriptRoot 'guncelle.py'
    $oldVersion = [string]$kurulu.version
    Write-Host "Mevcut sürüm: $oldVersion"
    Invoke-Adim $py @($helper, 'backup', '--data-dir', $dd)
    $pythonStamp = Join-Path $dd '.guncelleme-python-sha256'
    if (-not (Test-Path -LiteralPath $pythonStamp)) {
        [IO.File]::WriteAllText($pythonStamp, (Get-PythonKilit $kurulu.installPath))
    }
    Invoke-Adim $script:ClaudeExe @('plugin', 'marketplace', 'update', $PazarAdi)
    Invoke-Adim $script:ClaudeExe @('plugin', 'update', "$PluginAdi@$PazarAdi", '--scope', 'user')
    $kurulu = Get-KuruluPlugin
    if (-not $kurulu -or -not $kurulu.installPath) { throw 'Güncellenen plugin bilgisi okunamadı.' }
    $root = [string]$kurulu.installPath
    # Özellik bulunmadan başarı yazılmaz: yayımlanmamış/eski sürüme güncelleme anlaşılır biçimde durur.
    if (-not (Test-Path -LiteralPath (Join-Path $root 'hooks\error_notify.py'))) {
        throw 'Depodaki sürüm yeni müşteri güncellemesini desteklemiyor. Sağlayıcınızın yeni sürümü yayımlaması gerekiyor.'
    }
    $want = Get-PythonKilit $root
    if ((Get-Content -LiteralPath $pythonStamp -Raw).Trim() -ne $want) {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Değişen Python bağımlılıkları için uv bulunamadı.' }
        Write-Host 'Değişen Python bağımlılıkları alınıyor...'
        $env:UV_PROJECT_ENVIRONMENT = Join-Path $dd '.venv'
        $env:UV_LINK_MODE = 'copy'
        Invoke-Adim 'uv' @('sync', '--project', (Join-Path $root 'servers\ad_memory'), '--frozen', '--no-install-project', '--python', $py)
        [IO.File]::WriteAllText($pythonStamp, $want)
    } else { Write-Host 'Python bağımlılıkları aynı; atlandı.' }
    $nd = Join-Path $dd '.node'
    $tpl = Join-Path $root 'templates\remotion'
    $nodeStamp = Join-Path $nd '.kilit-sha256'
    $nodeHash = Get-Sha (Join-Path $tpl 'package-lock.json')
    $have = if (Test-Path -LiteralPath $nodeStamp) { (Get-Content -LiteralPath $nodeStamp -Raw).Trim() } else { '' }
    if ($have -ne $nodeHash -or -not (Test-Path -LiteralPath (Join-Path $nd 'node_modules\remotion'))) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Değişen video bağımlılıkları için npm bulunamadı.' }
        Write-Host 'Değişen video bağımlılıkları alınıyor...'
        New-Item -ItemType Directory -Force -Path $nd | Out-Null
        Copy-Item -LiteralPath (Join-Path $tpl 'package.json'), (Join-Path $tpl 'package-lock.json') -Destination $nd -Force
        Push-Location $nd
        try { Invoke-Adim 'npm.cmd' @('ci', '--no-audit', '--no-fund') } finally { Pop-Location }
        [IO.File]::WriteAllText($nodeStamp, $nodeHash)
    } else { Write-Host 'Video bağımlılıkları aynı; atlandı.' }
    Invoke-Adim $py @($helper, 'finish', '--data-dir', $dd, '--plugin-root', $root, '--from-version', $oldVersion)
    Write-Host "GÜNCELLEME TAMAMLANDI: $($kurulu.version). Test çalıştırılmadı." -ForegroundColor Green
    Write-Host 'Claude uygulamasını yeniden açıp yeni bir oturumda reklam-atolyesi yazın.'
    Write-Host 'Kullanımda hata bildirimi görürseniz belirtilen hata kaydını sağlayıcınıza gönderin.'
    $code = 0
} catch {
    Write-Host "GÜNCELLEME TAMAMLANAMADI: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Bu hata mesajını ve aşağıdaki günlük dosyasını sağlayıcınıza gönderin.' -ForegroundColor Yellow
    Write-Host 'Sürüm veya bağımlılıklar kısmen değişmiş olabilir. Sorun giderildikten sonra guncelle.cmd yeniden çalıştırılabilir.'
} finally {
    if ($updateLock) { $updateLock.Dispose() }
    Write-Host "Günlük: $Gunluk"
    try { Stop-Transcript | Out-Null } catch { }
    if ($dd -and (Test-Path -LiteralPath $Gunluk)) {
        try {
            $logs = Join-Path $dd 'logs'
            New-Item -ItemType Directory -Force -Path $logs | Out-Null
            Copy-Item -LiteralPath $Gunluk -Destination $logs -Force
            Write-Host "Kalıcı günlük: $(Join-Path $logs ([IO.Path]::GetFileName($Gunluk)))"
        } catch { Write-Host "Günlük veri klasörüne kopyalanamadı; yukarıdaki geçici günlük dosyasını gönderin." }
    }
}
exit $code
