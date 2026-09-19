# Renders intro.html frame by frame with headless Chrome, then encodes an MP4 with ffmpeg inside WSL.
#   .\render.ps1                          full render, 1920x1080, 30 fps, 11.5 s  ->  tenure-intro.mp4
#   .\render.ps1 -Only 2500,5500,10000    just these instants (ms), as PNGs in .\stills, for a quick look
#   .\render.ps1 -Tag "tenure.xyz"        replaces the last line of the end card
param([int[]]$Only, [string]$Tag = "", [string]$End = "", [string]$Out = "tenure-intro.mp4",
      [int]$Fps = 30, [double]$Seconds = 16.0, [int]$Workers = 8)
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$page = "file:///" + (Join-Path $dir "intro.html").Replace("\", "/")
$q = ""
if ($Tag) { $q += "&tag=" + [uri]::EscapeDataString($Tag) }
if ($End) { $q += "&end=" + [uri]::EscapeDataString($End) }

function Shoot([int]$ms, [string]$out, [int]$slot) {
  $prof = Join-Path $env:TEMP "tenure-render-video-$slot"
  $a = @("--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--user-data-dir=`"$prof`"",
         "--force-device-scale-factor=1", "--window-size=1920,1080", "--virtual-time-budget=400",
         "--screenshot=`"$out`"", "`"$page`?t=$ms$q`"")
  Start-Process -FilePath $exe -ArgumentList $a -PassThru -WindowStyle Hidden
}

if ($Only) {
  $stills = Join-Path $dir "stills"; New-Item -ItemType Directory -Force $stills | Out-Null
  $i = 0
  $procs = foreach ($ms in $Only) { Shoot $ms (Join-Path $stills ("t_{0:D5}.png" -f $ms)) ($i++) }
  $procs | ForEach-Object { $_.WaitForExit(60000) | Out-Null }
  Get-ChildItem $stills -Filter *.png | ForEach-Object { $_.Name }
  return
}

$frames = Join-Path $dir "frames"
if (Test-Path $frames) { Get-ChildItem $frames -Filter *.png | Remove-Item -Confirm:$false }
New-Item -ItemType Directory -Force $frames | Out-Null
$total = [int][math]::Round($Fps * $Seconds)
$sw = [Diagnostics.Stopwatch]::StartNew()
for ($start = 0; $start -lt $total; $start += $Workers) {
  $procs = for ($k = 0; $k -lt $Workers -and ($start + $k) -lt $total; $k++) {
    $n = $start + $k
    Shoot ([int][math]::Round($n * 1000 / $Fps)) (Join-Path $frames ("f_{0:D4}.png" -f $n)) $k
  }
  $procs | ForEach-Object { $_.WaitForExit(90000) | Out-Null }
}
$got = (Get-ChildItem $frames -Filter *.png).Count
"frames: $got / $total in $([int]$sw.Elapsed.TotalSeconds)s"
if ($got -ne $total) { throw "missing frames" }

$w = (wsl -e wslpath -a "$dir").Trim()
wsl -e ffmpeg -y -loglevel error -framerate $Fps -i "$w/frames/f_%04d.png" -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -movflags +faststart "$w/$Out"
wsl -e ffprobe -v error -show_entries "format=duration,size:stream=codec_name,width,height,r_frame_rate" -of "default=nw=1" "$w/$Out"
