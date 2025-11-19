#!/usr/bin/env python3
"""HTTP server for BGA02 metrics on port 8889"""
import serial
import time
import yaml
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import threading

# Load configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

# BGA Configuration from devices.yaml
COM_PORT = config['devices']['BGA02']['com_port']
BAUD_RATE = config['devices']['BGA02']['baud_rate']
HTTP_PORT = config['devices']['BGA02']['http_port']
GASES = {"7782-44-7": "O2", "1333-74-0": "H2", "7727-37-9": "N2"}
OVERLOAD = 9.9E37

# Global variables to store latest readings
latest_data = {
    "connected": False,
    "primary_gas": "NA",
    "secondary_gas": "NA", 
    "purity": None,
    "uncertainty": None,
    "temperature": None,
    "pressure": None
}
data_lock = threading.Lock()

# Command queue for external control
command_queue = []
command_lock = threading.Lock()

def cmd(ser, text, read=True):
    """Send command to BGA and optionally read response"""
    ser.write((text + "\r").encode())
    time.sleep(0.05)
    if not read:
        return None
    try:
        data = ser.read(ser.in_waiting or 1024).decode().strip()
        return data.split('\n')[-1] if data else None
    except:
        return None

def get_num(text):
    """Extract number from response, handle overload values"""
    if not text:
        return None
    for part in text.replace('%', '').split():
        try:
            val = float(part)
            if val >= OVERLOAD:
                return 0.0
            return val
        except:
            pass
    return None

def poll_bga():
    """Continuously poll BGA and update global data"""
    global latest_data, command_queue
    
    while True:
        try:
            # Connect to BGA
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.2)
            
            while True:
                # Process any pending commands first
                with command_lock:
                    if command_queue:
                        command = command_queue.pop(0)
                        print(f"  Sending command: {command}")
                        cmd(ser, command, read=False)
                
                # Read all parameters
                pg = cmd(ser, "GASP?")
                sg = cmd(ser, "GASS?")
                
                pur = get_num(cmd(ser, "RATO? 1%"))
                unc = get_num(cmd(ser, "UNCT?%"))
                tc = get_num(cmd(ser, "TCEL? C"))
                ps = get_num(cmd(ser, "PRES?"))
                
                # Update global data
                with data_lock:
                    # Check if we have valid data (not disconnected)
                    if pg is None and sg is None and all(v is None for v in [pur, unc, tc, ps]):
                        latest_data["connected"] = False
                    else:
                        latest_data["connected"] = True
                        latest_data["primary_gas"] = pg if pg else "NA"
                        latest_data["secondary_gas"] = sg if sg else "NA"
                        latest_data["purity"] = pur
                        latest_data["uncertainty"] = unc
                        latest_data["temperature"] = tc
                        latest_data["pressure"] = ps
                
                time.sleep(0.5)
                
        except Exception as e:
            # Connection failed, mark as disconnected
            with data_lock:
                latest_data["connected"] = False
            time.sleep(5)  # Wait before reconnecting

class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler for metrics endpoint"""
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/metrics':
            self.send_metrics()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests for command endpoint"""
        if self.path == '/command':
            # Read command from request body
            content_length = int(self.headers.get('Content-Length', 0))
            command = self.rfile.read(content_length).decode().strip()
            
            # Add to command queue
            with command_lock:
                command_queue.append(command)
            
            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)
    
    def send_metrics(self):
        """Send metrics in InfluxDB line protocol format"""
        with data_lock:
            # Don't send data if disconnected
            if not latest_data["connected"]:
                self.send_response(204)  # No Content
                self.end_headers()
                return
            
            # Build metrics string
            metrics = []
            
            # Add gas type fields (as tags in the metric line)
            gas_tags = f'primary_gas={latest_data["primary_gas"]},secondary_gas={latest_data["secondary_gas"]}'
            
            # Add numeric measurements
            fields = []
            if latest_data["purity"] is not None:
                fields.append(f'purity={latest_data["purity"]:.3f}')
            if latest_data["uncertainty"] is not None:
                fields.append(f'uncertainty={latest_data["uncertainty"]:.3f}')
            if latest_data["temperature"] is not None:
                fields.append(f'temperature={latest_data["temperature"]:.3f}')
            if latest_data["pressure"] is not None:
                fields.append(f'pressure={latest_data["pressure"]:.3f}')
            
            if fields:
                # Format: measurement,tag1=value1,tag2=value2 field1=value1,field2=value2
                metric_line = f'bga_metrics,{gas_tags} {",".join(fields)}'
                metrics.append(metric_line)
        
        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write('\n'.join(metrics).encode() + b'\n')
    
    def log_message(self, format, *args):
        """Suppress request logging"""
        pass

def main():
    """Main entry point"""
    # Start BGA polling thread
    poll_thread = threading.Thread(target=poll_bga, daemon=True)
    poll_thread.start()
    
    # Start HTTP server
    server = HTTPServer(('localhost', HTTP_PORT), MetricsHandler)
    print(f"BGA02 HTTP server started on port {HTTP_PORT}")
    print(f"Polling BGA on {COM_PORT} at {BAUD_RATE} baud")
    print(f"Config: {CONFIG_PATH}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

if __name__ == "__main__":
    main()