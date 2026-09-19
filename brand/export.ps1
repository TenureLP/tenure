# Rebuilds the SVGs in WSL, then rasterises them with headless Chrome (throwaway profile).
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wslDir = (wsl -e wslpath -a "$dir").Trim()
wsl -e python3 "$wslDir/build.py" @args

$exe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profileDir = Join-Path $env:TEMP "claude-headless-profile"
$jobs = @(
  @{ svg = "logo-mark.svg"; png = "logo-mark-1024.png"; w = 512; h = 512; scale = 2 },
  @{ svg = "logo-mark.svg"; png = "logo-mark-512.png"; w = 512; h = 512; scale = 1 },
  @{ svg = "logo-avatar.svg"; png = "logo-avatar-1024.png"; w = 512; h = 512; scale = 2 },
  @{ svg = "logo-avatar.svg"; png = "logo-avatar-400.png"; w = 400; h = 400; scale = 1 },
  @{ svg = "logo-horizontal-dark.svg"; png = "logo-horizontal-dark.png"; w = 1200; h = 400; scale = 2 },
  @{ svg = "logo-horizontal-light.svg"; png = "logo-horizontal-light.png"; w = 1200; h = 400; scale = 2 },
  @{ svg = "banner-1500x500.svg"; png = "banner-1500x500.png"; w = 1500; h = 500; scale = 1 },
  @{ svg = "banner-t1.svg"; png = "banner-t1.png"; w = 1500; h = 500; scale = 1 },
  @{ svg = "banner-t2.svg"; png = "banner-t2.png"; w = 1500; h = 500; scale = 1 },
  @{ svg = "banner-t3.svg"; png = "banner-t3.png"; w = 1500; h = 500; scale = 1 },
  @{ svg = "_sheet.svg"; png = "_sheet.png"; w = 1000; h = 660; scale = 1 }
)
foreach ($j in $jobs) {
  $src = "file:///" + (Join-Path $dir $j.svg).Replace("\", "/")
  $out = Join-Path $dir $j.png
  $a = @("--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--user-data-dir=`"$profileDir`"",
         "--default-background-color=00000000", "--force-device-scale-factor=$($j.scale)",
         "--window-size=$($j.w),$($j.h)", "--screenshot=`"$out`"", "`"$src`"")
  $p = Start-Process -FilePath $exe -ArgumentList $a -PassThru -WindowStyle Hidden
  $p.WaitForExit(40000) | Out-Null
  "{0,-32} {1}" -f $j.png, (Get-Item $out).LastWriteTime.ToString("HH:mm:ss")
}
