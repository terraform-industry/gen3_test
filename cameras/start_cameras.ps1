# Start cameras and arrange in 2x3 grid on 3440x1440 monitor
$VLC = "C:\Program Files\VideoLAN\VLC\vlc.exe"

# Load camera URLs from devices.yaml using simple parsing
$configPath = Join-Path $PSScriptRoot "..\MK1_AWE\config\devices.yaml"
$yamlContent = Get-Content $configPath

# Simple YAML parsing for camera URLs (avoids module dependency)
$cameras = @()
$inCamerasSection = $false
foreach ($line in $yamlContent) {
    if ($line -match '^\s+cameras:') {
        $inCamerasSection = $true
        continue
    }
    if ($inCamerasSection) {
        # Exit cameras section if we hit another top-level key
        if ($line -match '^\s{0,2}\w+:' -and $line -notmatch '^\s+cam\d+:' -and $line -notmatch '^\s+url:') {
            break
        }
        # Extract URL
        if ($line -match 'url:\s+"(.+)"') {
            $cameras += $matches[1]
        }
    }
}

Write-Host "Loaded $($cameras.Count) cameras from devices.yaml"

# Grid positions for 2x3 layout on 2nd monitor (3440x1440)
# Monitor offset: 3440 pixels (moves to 2nd screen)
# Position [0,0] is reserved for GUI (top-left)
# Overlap windows to eliminate gaps
$monitor_offset = 3440
$width = 1155   # Slightly larger to cover gaps
$height = 728   # Slightly larger to cover gaps
$overlap = 8    # Pixels to overlap
$positions = @(
    # [0,0] is GUI position (no VLC window)
    @{X=$monitor_offset+1147-$overlap; Y=0;          W=$width; H=$height},  # [1,0] Cam1
    @{X=$monitor_offset+2294-$overlap; Y=0;          W=$width; H=$height},  # [2,0] Cam2
    @{X=$monitor_offset+0;             Y=720-$overlap; W=$width; H=$height},  # [0,1] Cam3
    @{X=$monitor_offset+1147-$overlap; Y=720-$overlap; W=$width; H=$height},  # [1,1] Cam4
    @{X=$monitor_offset+2294-$overlap; Y=720-$overlap; W=$width; H=$height}   # [2,1] Cam5
)

# Windows API for window positioning
Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    public class Win32 {
        [DllImport("user32.dll")]
        public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, 
            int X, int Y, int cx, int cy, uint uFlags);
        
        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        
        public const uint SWP_NOZORDER = 0x0004;
        public const uint SWP_SHOWWINDOW = 0x0040;
        public const int SW_RESTORE = 9;
    }
"@

# Launch VLC windows
Write-Host "Launching camera streams..."
$processes = @()
foreach ($url in $cameras) {
    $proc = Start-Process -FilePath $VLC -ArgumentList $url -PassThru
    $processes += $proc
}

# Wait for windows to open
Start-Sleep -Seconds 3

# Get VLC windows and position them
Write-Host "Arranging windows..."
$vlcWindows = Get-Process vlc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }

for ($i = 0; $i -lt [Math]::Min($vlcWindows.Count, $positions.Count); $i++) {
    $hwnd = $vlcWindows[$i].MainWindowHandle
    $pos = $positions[$i]
    
    # Restore window if minimized
    [Win32]::ShowWindow($hwnd, [Win32]::SW_RESTORE) | Out-Null
    
    # Position and resize window
    [Win32]::SetWindowPos($hwnd, [IntPtr]::Zero, 
        $pos.X, $pos.Y, $pos.W, $pos.H, 
        [Win32]::SWP_NOZORDER -bor [Win32]::SWP_SHOWWINDOW) | Out-Null
}

Write-Host "Camera grid setup complete (2x3 layout)"

