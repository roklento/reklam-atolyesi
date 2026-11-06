<#
Reklam Atölyesi — eski kök kurulum betiği (2.10.14'ten beri yönlendirici).

Kurulumun tek kaynağı musteri-paketi\kur.ps1 dosyasıdır. Bu betik aynı parametreleri ona iletir; böylece kökten başlatılan kurulum da
tamamlanmış kurulumu güncelleyiciye yönlendirir ve yarım kalmış kurulumu kaldığı yerden sürdürür. İki ayrı kopya artık tutulmaz.
#>
param(
    [string]$DepoUrl = "https://github.com/roklento/reklam-atolyesi.git",
    [string]$PazarAdi = "reklam-atolyesi",
    [string]$VeriKlasoru = "",
    [switch]$DogrulamaYok
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$asil = Join-Path $PSScriptRoot "musteri-paketi\kur.ps1"
if (-not (Test-Path -LiteralPath $asil)) {
    Write-Host ""
    Write-Host "  [hata] Bu klasörde kurulum paketi yok. Sağlayıcınızın gönderdiği paketi bir klasöre çıkarıp oradaki kur.cmd dosyasına çift tıklayın." -ForegroundColor Red
    exit 1
}
Write-Host "Kurulum paketi musteri-paketi klasöründen çalıştırılıyor. Sonraki güncellemeler için o klasördeki guncelle.cmd dosyasını kullanın." -ForegroundColor Cyan
& $asil @PSBoundParameters
exit $LASTEXITCODE
