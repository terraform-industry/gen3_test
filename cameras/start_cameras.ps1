# Start cameras and arrange in 2x3 grid on 3440x1440 monitor
$VLC = "C:\Program Files\VideoLAN\VLC\vlc.exe"

# Camera URLs
$cameras = @(
    "rtsp://192.168.0.180:554/main/av",
    "rtsp://192.168.0.181:554/main/av",
    "rtsp://192.168.0.182:554/main/av",
    "rtsp://admin:Carbonneutral1!@192.168.0.100:554/h264Preview_01_main",
    "rtsp://admin:Carbonneutral1!@192.168.0.101:554/h264Preview_01_main",
    "rtsp://admin:Carbonneutral1!@192.168.0.3:554/h264Preview_01_main"
)

# Grid positions for 2x3 layout (3440x1440 monitor)
$width = 1147
$height = 720
$positions = @(
    @{X=0;    Y=0;   W=$width; H=$height},  # Top-left
    @{X=1147; Y=0;   W=$width; H=$height},  # Top-center
    @{X=2294; Y=0;   W=$width; H=$height},  # Top-right
    @{X=0;    Y=720; W=$width; H=$height},  # Bottom-left
    @{X=1147; Y=720; W=$width; H=$height},  # Bottom-center
    @{X=2294; Y=720; W=$width; H=$height}   # Bottom-right
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

