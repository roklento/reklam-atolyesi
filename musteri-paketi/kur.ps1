<#
Reklam Atölyesi — Windows ilk kurulum betiği (müşteri paketi).

Çift tıklama için kur.cmd kullanın. Tamamlanmış bir kurulumun güncellemesi guncelle.cmd ile yapılır. Yarıda kalmış bir ilk kurulum
(ör. doğrulama geçmedi, pencere kapandı) bu betikle kaldığı yerden sürdürülür:
  1. git ve Claude Code'u denetler (eksikse kurar)
  2. GitHub erişimini doğrular (ilk seferde tarayıcıda GitHub girişi açılır)
  3. Reklam Atölyesi marketplace'ini ekler ya da günceller
  4. Plugin'i kurar (veri klasörü sorulur); yarım kurulumda kayıtlı veri klasörüyle plugin'i günceller
  5. Plugin'in kendi kurulum adımlarını çalıştırır: araçlar, Python ve Remotion bağımlılıkları, bu bilgisayarda doğrulama
#>
param(
    [string]$DepoUrl = "https://github.com/roklento/reklam-atolyesi.git",
    [string]$PazarAdi = "reklam-atolyesi",
    [string]$VeriKlasoru = "",
    [switch]$DogrulamaYok   # destek/tanı: yalnızca kurulum adımları, bu bilgisayardaki doğrulama atlanır (kurulum tamamlanmış sayılmaz)
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$PluginAdi = "reklam-atolyesi"
$EnDusukClaude = [version]"2.1.285"

function Write-Adim([string]$t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Write-Tamam([string]$t) { Write-Host "  [tamam] $t" -ForegroundColor Green }
function Write-Uyari([string]$t) { Write-Host "  [uyarı] $t" -ForegroundColor Yellow }
function Stop-Kurulum([string]$t) {
    Write-Host ""; Write-Host "  [hata] $t" -ForegroundColor Red
    Write-Host "  Bu hata mesajını ve günlük dosyasını sağlayıcınıza gönderin."
    Write-Host "  Kurulum günlüğü: $script:Gunluk"
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
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
function Get-ClaudeSurum([string]$exe) {
    $v = (& $exe --version) -join " "
    if ($v -match "(\d+\.\d+\.\d+)") { return [version]$Matches[1] }
    return [version]"0.0.0"
}
function Invoke-Claude([string[]]$argv) {
    # Çıktı ekrana gider; işlevin dönüş değeri yalnızca çıkış kodudur.
    & $script:ClaudeExe @argv | Out-Host
    return $LASTEXITCODE
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
function Set-EksikAyarlar {
    # Kullanıcının hiç ayarlamadığı seçenekler plugin'in kendi varsayılanlarıyla kaydedilir; ayarlanmış değerlere dokunulmaz.
    $a = Get-PluginAyarlari
    if (-not $a -or -not $a.unconfigured) { return }
    $vals = [ordered]@{}
    foreach ($k in @($a.unconfigured)) {
        $s = $a.schema.$k
        if ($s -and ($s.PSObject.Properties.Name -contains "default")) { $vals[$k] = [System.Convert]::ToString($s.default, [Globalization.CultureInfo]::InvariantCulture) }
    }
    if ($vals.Count -eq 0) { return }
    # --values-stdin yalnızca dizge değerli bir JSON nesnesi kabul eder ve girdiyi dosya yönlendirmesiyle almalıdır
    # (Windows'ta boru hattıyla verilen girdi okunmuyor). Komut satırı cmd'ye bütünüyle bizce kurulur.
    $json = ConvertTo-Json $vals -Compress
    $tmp = Join-Path $env:TEMP ("reklam-atolyesi-ayarlar-{0}.json" -f [guid]::NewGuid().ToString("N"))
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding $false))
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/d /s /c `"`"$script:ClaudeExe`" plugin configure `"$PluginAdi@$PazarAdi`" --values-stdin < `"$tmp`"`""
    $psi.UseShellExecute = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.WaitForExit()
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 0) { Write-Uyari "Varsayılan ayarlar kaydedilemedi; Claude'da /plugin → reklam-atolyesi → Configure ile ayarlayabilirsiniz." }
    else { Write-Tamam ("Varsayılan ayarlar: " + (($vals.Keys | ForEach-Object { "$_=$($vals[$_])" }) -join ", ")) }
}
function Get-OnerilenVeriKlasoru {
    $best = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Sort-Object FreeSpace -Descending | Select-Object -First 1
    $drive = if ($best) { $best.DeviceID } else { $env:SystemDrive }
    return "$drive\ReklamAtolyesi\veri"
}

# Beklenmeyen hata (ör. alt betikte) günlüğü kapatıp açık bir mesajla durur.
trap { Stop-Kurulum ("Beklenmeyen hata: " + $_.Exception.Message + " (satır " + $_.InvocationInfo.ScriptLineNumber + ")") }

# --- 0 -------------------------------------------------------------------------------------------------------------------
$script:Gunluk = Join-Path $env:TEMP ("reklam-atolyesi-kurulum-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
try { Start-Transcript -Path $script:Gunluk | Out-Null } catch { }
Write-Host ""
Write-Host "  Reklam Atölyesi — ilk kurulum" -ForegroundColor White
Write-Host "  Bu pencereyi kurulum bitene kadar kapatmayın. İlk kurulum internet hızına göre 20-40 dakika sürer."
if ($DepoUrl -like "__*" -or $PazarAdi -like "__*") { Stop-Kurulum "Bu betik yayın betiğiyle hazırlanmamış (depo adresi boş). Sağlayıcınızdan güncel kur.cmd / kur.ps1 isteyin." }
if (-not [Environment]::Is64BitOperatingSystem) { Stop-Kurulum "64 bit Windows gerekli." }

# --- 1. git ve Claude Code ------------------------------------------------------------------------------------------------
Write-Adim "1/5 git ve Claude Code"
Update-YolDegiskeni
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Kurulum "git gerekli ama winget yok. Microsoft Store'dan 'Uygulama Yükleyicisi'ni kurun ya da https://git-scm.com adresinden git'i kurup tekrar çalıştırın."
    }
    Write-Host "  git kuruluyor ..."
    & winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements --silent
    Update-YolDegiskeni
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Stop-Kurulum "git kurulamadı. https://git-scm.com adresinden kurup tekrar çalıştırın." }
}
Write-Tamam ((& git --version) -join " ")

$script:ClaudeExe = Find-Claude
if (-not $script:ClaudeExe) {
    Write-Uyari "Claude Code komut satırı bulunamadı."
    if (-not (Read-EvetHayir "Anthropic'in resmi kurulum betiğiyle (claude.ai/install.ps1) Claude Code kurulsun mu?")) {
        Stop-Kurulum "Claude Code gerekli. https://code.claude.com adresinden kurup tekrar çalıştırın."
    }
    # Alt kapsamda çalıştırılır: resmi betik Set-StrictMode -Version Latest açar; bu kapsama sızarsa sonraki adımlar katı modda çalışır.
    & { Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression }
    Set-StrictMode -Off
    Update-YolDegiskeni
    $script:ClaudeExe = Find-Claude
    if (-not $script:ClaudeExe) { Stop-Kurulum "Claude Code kurulamadı." }
}
$cv = Get-ClaudeSurum $script:ClaudeExe
if ($cv -lt $EnDusukClaude) {
    Write-Uyari "Claude Code $cv eski (en az $EnDusukClaude gerekli); güncelleniyor ..."
    & $script:ClaudeExe update
    $cv = Get-ClaudeSurum $script:ClaudeExe
    if ($cv -lt $EnDusukClaude) { Stop-Kurulum "Claude Code güncellenemedi ($cv). Claude masaüstü uygulamasını ya da Claude Code'u güncelleyip tekrar çalıştırın." }
}
Write-Tamam "Claude Code $cv ($script:ClaudeExe)"

if (Get-KuruluPlugin) {
    # Yalnızca doğrulaması tamamlanmış kurulum guncelle.cmd'ye yönlendirilir. Doğrulama geçmeden kalan kurulumda veritabanı olmayabilir;
    # guncelle.cmd ise veritabanı ister. Yönlendirme iki betik arasında döngü kurmasın diye yarım kurulum burada sürdürülür.
    $kayitli = Get-KayitliVeriKlasoru
    if ($kayitli -and (Test-Path -LiteralPath (Join-Path $kayitli ".kurulum-statik-tamam"))) {
        Write-Host 'Reklam Atölyesi zaten kurulu. Güncelleme için guncelle.cmd dosyasını kullanın.' -ForegroundColor Yellow
        try { Stop-Transcript | Out-Null } catch { }
        exit 0
    }
    Write-Uyari "Önceki ilk kurulum tamamlanmamış; kaldığı yerden sürdürülüyor."
}

# --- 2. GitHub erişimi ----------------------------------------------------------------------------------------------------
Write-Adim "2/5 Depo erişimi"
Write-Host "  İlk seferde tarayıcıda GitHub girişi açılabilir; size davet gönderilen GitHub hesabıyla giriş yapın."
& git ls-remote --exit-code $DepoUrl HEAD | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-Kurulum ("Depoya erişilemedi: $DepoUrl`n  GitHub hesabınızın bu depoya erişimi olmalı (sağlayıcınızın gönderdiği daveti GitHub'da kabul edin) " +
        "ve doğru hesapla giriş yapmış olmalısınız. Yanlış hesapla giriş yaptıysanız Windows 'Kimlik Bilgileri Yöneticisi'nden github.com kaydını silip tekrar deneyin.")
}
Write-Tamam "Depoya erişim var"

# --- 3. Marketplace -------------------------------------------------------------------------------------------------------
Write-Adim "3/5 Reklam Atölyesi marketplace'i"
$mk = Get-ClaudeJson @("plugin", "marketplace", "list", "--json")
$var = $false
if ($mk) { foreach ($m in $mk) { if ($m -and $m.name -eq $PazarAdi) { $var = $true } } }
if ($var) {
    if ((Invoke-Claude @("plugin", "marketplace", "update", $PazarAdi)) -ne 0) { Stop-Kurulum "Marketplace güncellenemedi." }
    Write-Tamam "Güncellendi"
} else {
    if ((Invoke-Claude @("plugin", "marketplace", "add", $DepoUrl)) -ne 0) { Stop-Kurulum "Marketplace eklenemedi ($DepoUrl)." }
    Write-Tamam "Eklendi"
}

# --- 4. Plugin -----------------------------------------------------------------------------------------------------------
Write-Adim "4/5 Plugin"
$kurulu = Get-KuruluPlugin
$guncelleme = $false
if ($kurulu) {
    # Yarım kalmış ilk kurulum: kayıtlı veri klasörüyle sürdürülür. Güncelleme kipini kurulum.ps1 veritabanının varlığına göre kendisi seçer.
    $dd = Get-KayitliVeriKlasoru
    if (-not $dd) { Stop-Kurulum "Plugin kurulu ama kayıtlı veri klasörü okunamadı. Claude'da /plugin → reklam-atolyesi → Configure ile veri klasörünü kontrol edin." }
    Write-Host "  Kurulu sürüm: $($kurulu.version) · veri klasörü: $dd"
    if ((Invoke-Claude @("plugin", "update", "$PluginAdi@$PazarAdi", "--scope", "user")) -ne 0) { Stop-Kurulum "Plugin güncellenemedi." }
    if (-not $kurulu.enabled) { Invoke-Claude @("plugin", "enable", "$PluginAdi@$PazarAdi", "--scope", "user") | Out-Null }
} else {
    $dd = $VeriKlasoru
    if (-not $dd) {
        $oneri = Get-OnerilenVeriKlasoru
        Write-Host "  Veri klasörü: markalarınızın verisi, çekimler, render'lar ve bağımlılıklar burada tutulur (önerilen ≥ 50 GB boş alan)."
        $g = Read-Host "  Veri klasörü [Enter = $oneri]"
        $dd = if ($g -and $g.Trim()) { $g.Trim().Trim('"') } else { $oneri }
    }
    if (-not [System.IO.Path]::IsPathRooted($dd)) { Stop-Kurulum ("Veri klasörü tam yol olmalı (ör. " + (Get-OnerilenVeriKlasoru) + ").") }
    $dd = [System.IO.Path]::GetFullPath($dd)
    if ($dd.TrimEnd("\") -eq [System.IO.Path]::GetPathRoot($dd).TrimEnd("\")) { Stop-Kurulum "Sürücünün kökü veri klasörü olamaz; bir alt klasör verin." }
    New-Item -ItemType Directory -Force -Path $dd | Out-Null
    if ((Invoke-Claude @("plugin", "install", "$PluginAdi@$PazarAdi", "--scope", "user", "--config", "data_dir=$dd")) -ne 0) { Stop-Kurulum "Plugin kurulamadı." }
}
Set-EksikAyarlar
$kurulu = Get-KuruluPlugin
if (-not $kurulu -or -not $kurulu.installPath) { Stop-Kurulum "Plugin kurulumu doğrulanamadı (claude plugin list)." }
Write-Tamam "reklam-atolyesi $($kurulu.version) · $($kurulu.installPath)"

# --- 5. Plugin'in kurulum adımları -----------------------------------------------------------------------------------------
Write-Adim "5/5 Araçlar, bağımlılıklar ve doğrulama"
$ic = Join-Path $kurulu.installPath "scripts\setup\windows\kurulum.ps1"
if (-not (Test-Path $ic)) { Stop-Kurulum "Plugin içinde kurulum adımları bulunamadı: $ic" }
$p = @{ DataDir = $dd; Claude = $script:ClaudeExe }
if ($guncelleme) { $p.Guncelleme = $true }
if ($DogrulamaYok) { $p.DogrulamaYok = $true }
& $ic @p
if ($LASTEXITCODE -ne 0) { Stop-Kurulum "Kurulum adımları tamamlanamadı (yukarıdaki mesaja bakın)." }

Write-Host ""
Write-Host "  $(if ($DogrulamaYok) { "KURULUM ADIMLARI TAMAMLANDI (doğrulama atlandı; tamamlamak için -DogrulamaYok olmadan yeniden çalıştırın)" } else { "KURULUM TAMAMLANDI" })" -ForegroundColor Green
if (-not $DogrulamaYok) {
    Write-Host "  1. Claude masaüstü uygulamasını tamamen kapatın (sistem tepsisindeki simgeden 'Çıkış') ve yeniden açın."
    Write-Host "  2. Yeni bir oturum açıp yalnızca şunu yazın:  reklam-atolyesi"
    Write-Host "  3. İlk açılışta ElevenLabs ve Meta (salt okuma) hesaplarınızı bağlamanız istenecek."
    if ($guncelleme) { Write-Host "  Güncellemeden sonra ilk açılışta canlı kontroller yeniden yapılır." }
}
Write-Host "  Kurulum günlüğü: $script:Gunluk"
try { Stop-Transcript | Out-Null } catch { }
exit 0
