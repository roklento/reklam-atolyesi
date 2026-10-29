<#
reklam-atolyesi - Windows araç ve bağımlılık kurulumu (spec 12.2, 12.6, 12.9; dagitilan kurulum).

Plugin ile birlikte sürümlenir; kök kurulum betiği (kur.ps1) plugin'i Claude Code'a kurduktan ya da güncelledikten sonra
yüklü sürümün klasöründen çağırır. Yaptıkları:
  1. Araçlar: Node.js >= 22, uv, FFmpeg tam sürüm (vidstab, zscale ...). Eksik olan winget ile kurulur.
  2. Disk: data_dir sürücüsünde >= 50 GB, sistem sürücüsünde >= 10 GB; azsa kullanıcı açıkça kabul ederse sapma olarak kaydedilir.
  3. Python 3.12 sanal ortamı <data_dir>\.venv (yalnızca bağımlılıklar; kod plugin klasöründen çalışır).
  4. Remotion bağımlılıkları <data_dir>\.node (kilit dosyasına göre; değişmediyse atlanır).
  5. Makinede doğrulama: scripts/setup/kurulum_dogrula.py (duman testi, render, galeri, doctor).
Kullanıcı verisine (profiller, kampanyalar, veritabanı) dokunmaz; güncellemede önce veritabanı yedeği alınır.
#>
param(
    [Parameter(Mandatory = $true)][string]$DataDir,
    [string]$Claude = "",
    [switch]$Guncelleme,
    [switch]$DogrulamaYok,
    # ~/.claude/skills altında çakışan genel skill'ler: sor (pencerede sorulur), tasi (yedeğe taşı), birak (sapma olarak kaydet).
    # Eski kur.ps1 bu parametreyi vermez; varsayılan "sor" kurulum penceresinde kullanıcıya sorar.
    [ValidateSet("sor", "tasi", "birak")][string]$GlobalSkills = "sor",
    # 1.6.0: video üretimi ya da ücretli/yazma sağlayıcısı olan öteki plugin'ler: sor (pencerede sorulur), devre-disi (claude plugin disable;
    # geri alınabilir), birak (sapma olarak kaydet). Eski kur.ps1 bu parametreyi vermez; varsayılan "sor".
    [ValidateSet("sor", "devre-disi", "birak")][string]$Plugins = "sor"
)

$ErrorActionPreference = "Stop"
# Çağıran betikten devralınan katı modu kapat: kur.ps1, Claude Code yoksa resmi install.ps1'i kendi kapsamında çalıştırır ve o betik
# Set-StrictMode -Version Latest açar. Katı mod alt betiklere geçer; boş dizi dönen işlevde .Count "özellik yok" hatası verip kurulumu
# 1/5'te durduruyordu (1.4.0, ilk kurulum). Bu satır yalnızca bu betiğin kapsamını etkiler.
Set-StrictMode -Off
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Version = (Get-Content (Join-Path $Root ".claude-plugin\plugin.json") -Raw -Encoding UTF8 | ConvertFrom-Json).version
$Allowed = @(".venv", ".node", "db", ".kurulum-statik-tamam", ".sessions", "logs", "backups", "memory", ".selftest")
$FfmpegFilters = @("vidstabdetect", "vidstabtransform", "zscale", "loudnorm", "lut3d", "sidechaincompress", "tonemap", "colorchannelmixer")

function Write-Adim([string]$t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Write-Tamam([string]$t) { Write-Host "  [tamam] $t" -ForegroundColor Green }
function Write-Uyari([string]$t) { Write-Host "  [uyarı] $t" -ForegroundColor Yellow }
function Stop-Kurulum([string]$t) { Write-Host ""; Write-Host "  [hata] $t" -ForegroundColor Red; exit 1 }

function Update-YolDegiskeni {
    # winget kurulumlarından sonra yeni PATH girdilerini bu oturuma alır (mevcut girdiler korunur).
    $parts = @()
    foreach ($scope in "Machine", "User") {
        $v = [Environment]::GetEnvironmentVariable("Path", $scope)
        if ($v) { $parts += $v.Split(";") }
    }
    $parts += $env:Path.Split(";")
    $seen = @{}
    $out = @()
    foreach ($p in $parts) {
        $q = $p.Trim()
        if ($q -and -not $seen.ContainsKey($q.ToLowerInvariant())) { $seen[$q.ToLowerInvariant()] = $true; $out += $q }
    }
    $env:Path = ($out -join ";")
}

function Test-Komut([string]$name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Install-Winget([string]$id, [string]$ad) {
    if (-not (Test-Komut "winget")) {
        Stop-Kurulum "$ad gerekli ama winget yok. Microsoft Store'dan 'Uygulama Yükleyicisi' (App Installer) uygulamasını kurup tekrar deneyin ya da $ad uygulamasını elle kurun."
    }
    Write-Host "  $ad kuruluyor (winget: $id) ..."
    & winget install --id $id -e --source winget --accept-source-agreements --accept-package-agreements --silent
    $code = $LASTEXITCODE
    Update-YolDegiskeni
    if ($code -ne 0) { Write-Uyari "winget çıkış kodu $code (zaten kurulu olabilir); aşağıda yeniden kontrol ediliyor." }
}

function Get-NodeMajor {
    if (-not (Test-Komut "node")) { return 0 }
    $v = (& node -v) 2>$null
    if ($v -match "^v(\d+)\.") { return [int]$Matches[1] }
    return 0
}

function Get-EksikFfmpegFiltreleri {
    if (-not (Test-Komut "ffmpeg")) { return $FfmpegFilters }
    $f = (& ffmpeg -hide_banner -filters) -join "`n"
    $miss = @()
    foreach ($x in $FfmpegFilters) { if ($f -notmatch "\s$x\s") { $miss += $x } }
    return $miss
}

function Get-BosGB([string]$path) {
    $drive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($path))
    $d = New-Object System.IO.DriveInfo($drive)
    return [math]::Round($d.AvailableFreeSpace / 1GB, 1)
}

function Read-EvetHayir([string]$soru) {
    for ($i = 0; $i -lt 5; $i++) {
        $r = Read-Host "$soru [E/H]"
        if ($null -eq $r) { return $false }  # girdi yok (etkileşimsiz): hayır sayılır
        $a = $r.Trim().ToLowerInvariant()
        if ($a -in @("e", "evet", "y", "yes")) { return $true }
        if ($a -in @("h", "hayir", "hayır", "n", "no")) { return $false }
    }
    return $false  # 5 geçersiz/boş yanıt: hayır sayılır
}

# --- 0. data_dir --------------------------------------------------------------------------------------------------------
Write-Adim "reklam-atolyesi $Version - araç ve bağımlılık kurulumu"
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
Write-Host "  Plugin klasörü : $Root"
Write-Host "  Veri klasörü   : $DataDir"
if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Force -Path $DataDir | Out-Null }
if (Test-Path (Join-Path $DataDir "db\ad-memory.sqlite")) { $Guncelleme = $true }
if (-not $Guncelleme) {
    $extra = @(Get-ChildItem -Force $DataDir | Where-Object { $Allowed -notcontains $_.Name } | ForEach-Object { $_.Name })
    if ($extra.Count -gt 0) {
        Stop-Kurulum ("Veri klasörü boş değil ve bir reklam-atolyesi kurulumu da değil (" + ($extra -join ", ") + "). Boş ya da yeni bir klasör seçin.")
    }
}
Write-Tamam ($(if ($Guncelleme) { "Mevcut kurulum: güncelleme modu (verileriniz korunur)" } else { "Yeni kurulum" }))

# --- 1. Araçlar ---------------------------------------------------------------------------------------------------------
Write-Adim "1/5 Araçlar"
Update-YolDegiskeni
if ((Get-NodeMajor) -lt 22) { Install-Winget "OpenJS.NodeJS.LTS" "Node.js LTS" }
$nm = Get-NodeMajor
if ($nm -lt 22) { Stop-Kurulum "Node.js 22 veya üzeri bulunamadı (bulunan: $nm). https://nodejs.org adresinden LTS sürümünü kurup tekrar deneyin." }
Write-Tamam ("Node.js " + (& node -v))

if (-not (Test-Komut "uv")) { Install-Winget "astral-sh.uv" "uv" }
if (-not (Test-Komut "uv")) { Stop-Kurulum "uv bulunamadı. https://docs.astral.sh/uv/ adresindeki Windows kurulumunu yapıp tekrar deneyin." }
Write-Tamam ((& uv --version) -join " ")

$miss = @(Get-EksikFfmpegFiltreleri)
if ($miss.Count -gt 0) {
    if (Test-Komut "ffmpeg") { Write-Uyari ("Mevcut FFmpeg'de eksik filtreler: " + ($miss -join ", ") + " - tam sürüm kuruluyor.") }
    Install-Winget "Gyan.FFmpeg" "FFmpeg (tam sürüm)"
    $miss = @(Get-EksikFfmpegFiltreleri)
}
if ($miss.Count -gt 0) {
    $where = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
    Stop-Kurulum ("FFmpeg tam sürüm gerekli; eksik filtreler: " + ($miss -join ", ") + ". PATH'teki ffmpeg: $where. " +
        "Daha eski bir ffmpeg PATH'te öne geçiyorsa kaldırın ya da https://www.gyan.dev/ffmpeg/builds/ 'full' sürümünü kurun.")
}
Write-Tamam ("FFmpeg: " + (Get-Command ffmpeg).Source)
if (-not (Test-Komut "git")) { Stop-Kurulum "git bulunamadı (kök kurulum betiği kurmuş olmalıydı)." }

# --- 2. Disk ------------------------------------------------------------------------------------------------------------
Write-Adim "2/5 Disk alanı"
$deviations = @()
$marker = Join-Path $DataDir ".kurulum-statik-tamam"
$accepted = @()
if (Test-Path $marker) {
    try { $accepted = @((Get-Content $marker -Raw -Encoding UTF8 | ConvertFrom-Json).accepted_deviations) } catch { $accepted = @() }
}
$checks = @(
    @{ key = "disk_data"; id = "data_drive_space"; gb = (Get-BosGB $DataDir); need = 50; label = "veri klasörünün sürücüsünde"; why = "4K ham çekim, ara dosyalar ve render için alan yetmeyebilir.";
       spec = "12.1, 12.10 (data_dir sürücüsünde >= 50 GB boş)" },
    @{ key = "disk_system"; id = "system_drive_space"; gb = (Get-BosGB ($env:SystemDrive + "\")); need = 10; label = "sistem sürücüsünde"; why = "Claude Code, plugin önbelleği, npm/uv önbellekleri ve sanal bellek için alan yetmeyebilir.";
       spec = "12.1, 12.10 (sistem sürücüsünde >= 10 GB boş; hata)" }
)
foreach ($c in $checks) {
    if ($c.gb -ge $c.need) { Write-Tamam ("{0} {1} GB boş" -f $c.label, $c.gb); continue }
    if ($accepted -contains $c.key) { Write-Uyari ("{0} {1} GB boş (önerilen {2} GB) - daha önce kabul edilmiş sapma" -f $c.label, $c.gb, $c.need); continue }
    Write-Uyari ("{0} yalnızca {1} GB boş; önerilen en az {2} GB. {3}" -f $c.label, $c.gb, $c.need, $c.why)
    if (-not (Read-EvetHayir "Yine de devam edilsin ve bu durum sapma olarak kaydedilsin mi?")) {
        Stop-Kurulum "Kurulum durduruldu. Yer açıp tekrar çalıştırın ya da boş alanı fazla olan bir sürücüde veri klasörü seçin."
    }
    $deviations += [ordered]@{
        id = $c.id; check = $c.key; spec = $c.spec
        deviation = ("Kurulumda {0} boş alan {1} GB idi (şart {2} GB). Kullanıcı kurulumun sürmesine açıkça karar verdi; doctor maddeyi kırmızı gösterir." -f $c.label, $c.gb, $c.need)
        decided_by = "user"; decided_at = (Get-Date -Format "yyyy-MM-dd"); status = "accepted"
    }
}
$devFile = ""
if ($deviations.Count -gt 0) {
    $devFile = Join-Path $env:TEMP ("reklam-atolyesi-sapmalar-{0}.json" -f (Get-Date -Format "yyyyMMddHHmmss"))
    [System.IO.File]::WriteAllText($devFile, (ConvertTo-Json @($deviations) -Depth 4), (New-Object System.Text.UTF8Encoding $false))
}

# --- 3. Python ortamı -----------------------------------------------------------------------------------------------------
Write-Adim "3/5 Python 3.12 ortamı (<veri>\.venv)"
$env:UV_PROJECT_ENVIRONMENT = Join-Path $DataDir ".venv"
$env:UV_LINK_MODE = "copy"
$env:UV_PYTHON_PREFERENCE = "only-managed"
& uv python install 3.12
if ($LASTEXITCODE -ne 0) { Stop-Kurulum "Python 3.12 indirilemedi (uv python install). İnternet bağlantısını kontrol edin." }
& uv sync --project (Join-Path $Root "servers\ad_memory") --frozen --no-install-project --python 3.12
if ($LASTEXITCODE -ne 0) { Stop-Kurulum "Python bağımlılıkları kurulamadı (uv sync)." }
$py = Join-Path $DataDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Stop-Kurulum "Sanal ortam oluşmadı: $py" }
Write-Tamam ((& $py --version) -join " ")
Remove-Item Env:\UV_PROJECT_ENVIRONMENT, Env:\UV_LINK_MODE, Env:\UV_PYTHON_PREFERENCE -ErrorAction SilentlyContinue

# --- 4. Remotion ------------------------------------------------------------------------------------------------------------
Write-Adim "4/5 Remotion bağımlılıkları (<veri>\.node)"
$nd = Join-Path $DataDir ".node"
New-Item -ItemType Directory -Force -Path $nd | Out-Null
$tpl = Join-Path $Root "templates\remotion"
$lockSha = (Get-FileHash (Join-Path $tpl "package-lock.json") -Algorithm SHA256).Hash
$stamp = Join-Path $nd ".kilit-sha256"
$have = if (Test-Path $stamp) { (Get-Content $stamp -Raw).Trim() } else { "" }
if ($have -eq $lockSha -and (Test-Path (Join-Path $nd "node_modules\remotion"))) {
    Write-Tamam "Değişiklik yok (kilit dosyası aynı)"
} else {
    Copy-Item (Join-Path $tpl "package.json") (Join-Path $nd "package.json") -Force
    Copy-Item (Join-Path $tpl "package-lock.json") (Join-Path $nd "package-lock.json") -Force
    Push-Location $nd
    try {
        & npm.cmd ci --no-audit --no-fund
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($code -ne 0) { Stop-Kurulum "npm ci başarısız (çıkış kodu $code). İnternet bağlantısını kontrol edip tekrar çalıştırın." }
    [System.IO.File]::WriteAllText($stamp, $lockSha, (New-Object System.Text.UTF8Encoding $false))
    Write-Tamam "Remotion kuruldu"
}

# --- 5. Doğrulama -------------------------------------------------------------------------------------------------------
if ($DogrulamaYok) { Write-Uyari "Doğrulama atlandı (-DogrulamaYok). Kurulum tamamlanmış sayılmaz."; exit 0 }
Write-Adim "5/5 Bu bilgisayarda doğrulama (yaklaşık 15-20 dk; ilk render tarayıcı bileşenini indirir)"
$args2 = @((Join-Path $Root "scripts\setup\kurulum_dogrula.py"), "--data-dir", $DataDir, "--etkilesimli", "--global-skills", $GlobalSkills,
           "--plugins", $Plugins)
if ($Claude) { $args2 += @("--claude", $Claude) }
if ($devFile) { $args2 += @("--deviations-json", $devFile) }
if ($Guncelleme) { $args2 += "--guncelleme" }
$env:PYTHONIOENCODING = "utf-8"
& $py @args2
$code = $LASTEXITCODE
if ($devFile) { Remove-Item $devFile -ErrorAction SilentlyContinue }
if ($code -ne 0) {
    Stop-Kurulum ("Doğrulama geçmedi. Ayrıntılar: $DataDir\logs\kurulum-dogrulama-*.json (en yenisi). " +
        "Bu dosyayı destek için sağlayıcınıza gönderebilirsiniz.")
}
Write-Tamam "Doğrulama geçti"
exit 0
