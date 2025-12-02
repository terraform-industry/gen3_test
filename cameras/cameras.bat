@echo off
set VLC="C:\Program Files\VideoLAN\VLC\vlc.exe"

start "" %VLC% "rtsp://192.168.0.180:554/main/av"
start "" %VLC% "rtsp://192.168.0.181:554/main/av"
start "" %VLC% "rtsp://192.168.0.182:554/main/av"
start "" %VLC% "rtsp://admin:Carbonneutral1!@192.168.0.100:554/h264Preview_01_main"
start "" %VLC% "rtsp://admin:Carbonneutral1!@192.168.0.101:554/h264Preview_01_main"
start "" %VLC% "rtsp://admin:Carbonneutral1!@192.168.0.3:554/h264Preview_01_main"