#!/usr/bin/env python3
"""
HTTP server for BGA01 metrics - writes directly to InfluxDB
Also exposes /metrics endpoint for debugging and /command for control
"""
import serial
import time
import json
import os
import yaml
from pathlib import Path
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
BGA_ID = "BGA01"
RECONNECT_DELAY = 5

# Load configuration
def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)

config = load_config()

# BGA Configuration from devices.yaml
COM_PORT = config['devices'][BGA_ID]['com_port']
BAUD_RATE = config['devices'][BGA_ID]['baud_rate']
HTTP_PORT = config['devices'][BGA_ID]['http_port']
GASES = {"7782-44-7": "O2", "1333-74-0": "H2", "7727-37-9": "N2"}
OVERLOAD = 9.9E37

# Bridge config
bridge_config = config.get('bridges', {}).get('bga01', {})
SAMPLE_RATE = bridge_config.get('sample_rate', 2)
BUFFER_SECONDS = bridge_config.get('buffer_seconds', 2)

# Global state
sample_buffer = deque(maxlen=SAMPLE_RATE * BUFFER_SECONDS)
device_online = False
data_lock = threading.Lock()
influx_write_api = None
influx_bucket = None
points_written = 0

# Command queue for external control
command_queue = []
command_lock = threading.Lock()


def setup_influxdb():
    """Setup InfluxDB client for direct writes"""
    global influx_write_api, influx_bucket
    
    system_config = config.get('system', {})
    influx_url = system_config.get('influxdb_url', 'http://localhost:8086')
    influx_org = system_config.get('influxdb_org', 'electrolyzer')
    influx_bucket = system_config.get('influxdb_bucket', 'electrolyzer_data')
    
    influx_token = os.environ.get('INFLUXDB_ADMIN_TOKEN', '')
    
    if not influx_token:
        env_path = CONFIG_PATH.parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith('INFLUXDB_ADMIN_TOKEN='):
                        influx_token = line.strip().split('=', 1)[1]
                        break
    
    if not influx_token:
        print("[WARN] INFLUXDB_ADMIN_TOKEN not set - direct writes disabled")
        return False
    
    try:
        client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
        influx_write_api = client.write_api(write_options=SYNCHRONOUS)
        print(f"[OK] Connected to InfluxDB at {influx_url}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to connect to InfluxDB: {e}")
        return False


def write_to_influxdb(samples):
    """Write batch of samples directly to InfluxDB"""
    global points_written
    
    if not influx_write_api or not influx_bucket:
        return False
    
    try:
        points = []
        for sample in samples:
            point = Point("bga_metrics") \
                .tag("bga_id", BGA_ID) \
                .tag("hardware", "bga244") \
                .tag("location", "gen3_test_rig") \
                .tag("primary_gas", sample['primary_gas']) \
                .tag("secondary_gas", sample['secondary_gas'])
            
            if sample['purity'] is not None:
                point = point.field("purity", float(sample['purity']))
            if sample['uncertainty'] is not None:
                point = point.field("uncertainty", float(sample['uncertainty']))
            if sample['temperature'] is not None:
                point = point.field("temperature", float(sample['temperature']))
            if sample['pressure'] is not None:
                point = point.field("pressure", float(sample['pressure']))
            
            point = point.time(sample['timestamp_ns'], WritePrecision.NS)
            points.append(point)
        
        influx_write_api.write(bucket=influx_bucket, record=points)
        points_written += len(points)
        return True
    except Exception as e:
        print(f"[ERROR] InfluxDB write failed: {e}")
        return False


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
    """Continuously poll BGA and write to InfluxDB"""
    global sample_buffer, device_online, command_queue
    
    write_batch_size = SAMPLE_RATE  # Write every ~1 second
    pending_samples = []
    
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Buffer size: {SAMPLE_RATE * BUFFER_SECONDS} samples ({BUFFER_SECONDS}s)")
    print(f"InfluxDB write batch: {write_batch_size} samples")
    
    while True:
        try:
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.2)
            print(f"[OK] Connected to {BGA_ID} on {COM_PORT}")
            device_online = True
            
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
                
                # Check if we have valid data
                if pg is None and sg is None and all(v is None for v in [pur, unc, tc, ps]):
                    device_online = False
                else:
                    device_online = True
                    sample = {
                        'timestamp_ns': time.time_ns(),
                        'primary_gas': pg if pg else "NA",
                        'secondary_gas': sg if sg else "NA",
                        'purity': pur,
                        'uncertainty': unc,
                        'temperature': tc,
                        'pressure': ps
                    }
                    
                    # Add to pending samples for InfluxDB write
                    pending_samples.append(sample)
                    
                    # Add to buffer for /metrics endpoint
                    with data_lock:
                        sample_buffer.append(sample)
                    
                    # Write to InfluxDB when we have enough samples
                    if len(pending_samples) >= write_batch_size:
                        write_to_influxdb(pending_samples)
                        pending_samples = []
                
                time.sleep(1.0 / SAMPLE_RATE)
                
        except Exception as e:
            device_online = False
            print(f"[ERROR] {BGA_ID} offline: {e}")
            print(f"  Retrying in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler for metrics endpoint"""
    
    def do_GET(self):
        if self.path == '/metrics':
            self.send_metrics()
        elif self.path == '/health':
            self.send_health()
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/command':
            content_length = int(self.headers.get('Content-Length', 0))
            command = self.rfile.read(content_length).decode().strip()
            
            with command_lock:
                command_queue.append(command)
            
            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)
    
    def send_metrics(self):
        with data_lock:
            if not device_online or len(sample_buffer) == 0:
                self.send_response(204)
                self.end_headers()
                return
            
            samples = list(sample_buffer)
        
        lines = []
        for sample in samples:
            gas_tags = f'primary_gas={sample["primary_gas"]},secondary_gas={sample["secondary_gas"]}'
            
            fields = []
            if sample["purity"] is not None:
                fields.append(f'purity={sample["purity"]:.3f}')
            if sample["uncertainty"] is not None:
                fields.append(f'uncertainty={sample["uncertainty"]:.3f}')
            if sample["temperature"] is not None:
                fields.append(f'temperature={sample["temperature"]:.3f}')
            if sample["pressure"] is not None:
                fields.append(f'pressure={sample["pressure"]:.3f}')
            
            if fields:
                line = f'bga_metrics,{gas_tags} {",".join(fields)} {sample["timestamp_ns"]}'
                lines.append(line)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write('\n'.join(lines).encode() + b'\n')
    
    def send_health(self):
        with data_lock:
            buffer_size = len(sample_buffer)
            buffer_max = sample_buffer.maxlen
        
        response = {
            'status': 'online' if device_online else 'offline',
            'device_online': device_online,
            'sample_rate': SAMPLE_RATE,
            'buffer_seconds': BUFFER_SECONDS,
            'buffer_size': buffer_size,
            'buffer_max': buffer_max,
            'buffer_pct': round(100 * buffer_size / buffer_max, 1) if buffer_max > 0 else 0,
            'influxdb_enabled': influx_write_api is not None,
            'points_written': points_written
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def log_message(self, format, *args):
        pass


def main():
    hw_max = bridge_config.get('hw_max_rate', 5)
    
    print(f"{BGA_ID} HTTP Bridge (Direct InfluxDB)")
    print(f"Config: {CONFIG_PATH}")
    print(f"Configured rate: {SAMPLE_RATE} Hz (hardware max: {hw_max} Hz)")
    print(f"Polling {BGA_ID} on {COM_PORT} at {BAUD_RATE} baud")
    print(f"Endpoints: http://localhost:{HTTP_PORT}/metrics, /health, /command")
    print()
    
    # Setup InfluxDB direct writes
    setup_influxdb()
    
    # Start BGA polling thread
    poll_thread = threading.Thread(target=poll_bga, daemon=True)
    poll_thread.start()
    
    # Start HTTP server
    server = HTTPServer(('0.0.0.0', HTTP_PORT), MetricsHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
