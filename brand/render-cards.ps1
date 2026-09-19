# Builds the post cards in WSL, then rasterises them with headless Chrome (throwaway profile).
# Same chain as export.ps1, kept separate so a card change does not re-render every logo.
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wslDir = (wsl -e wslpath -a "$dir").Trim()
wsl -e python3 "$wslDir/cards.py"

$exe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profileDir = Join-Path $env:TEMP "tenure-render-profile"

Get-ChildItem -Path $dir -Filter "card-*.html" | ForEach-Object {
  $png = [IO.Path]::ChangeExtension($_.FullName, ".png")
  $src = "file:///" + $_.FullName.Replace("\", "/")
  $a = @("--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         "--user-data-dir=`"$profileDir`"", "--force-device-scale-factor=1",
         "--window-size=1600,900", "--screenshot=`"$png`"", "`"$src`"")
  $p = Start-Process -FilePath $exe -ArgumentList $a -PassThru -WindowStyle Hidden
  $p.WaitForExit(40000) | Out-Null
  "{0,-30} {1}" -f (Split-Path $png -Leaf), (Get-Item $png).Length
}
