#!/usr/bin/env python3
"""
PSU Modbus RTU HTTP Bridge
Reads PSU data via RS485/USB and writes directly to InfluxDB
Also exposes /metrics endpoint for debugging and /command for control
"""

import minimalmodbus
import yaml
import time
import os
import threading
import queue
from collections import deque
from flask import Flask, Response, request, jsonify
from pathlib import Path
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
RECONNECT_DELAY = 5  # seconds

app = Flask(__name__)

# Global state
sample_buffer = None  # Will be initialized as deque
device_online = False
data_lock = threading.Lock()
command_queue = queue.Queue()
influx_write_api = None
influx_bucket = None
points_written = 0

# Config values loaded at startup
SAMPLE_RATE = 8
BUFFER_SECONDS = 2


def load_config():
    """Load configuration from devices.yaml"""
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)
    return config


def setup_influxdb():
    """Setup InfluxDB client for direct writes"""
    global influx_write_api, influx_bucket
    
    config = load_config()
    system_config = config.get('system', {})
    
    influx_url = system_config.get('influxdb_url', 'http://localhost:8086')
    influx_org = system_config.get('influxdb_org', 'electrolyzer')
    influx_bucket = system_config.get('influxdb_bucket', 'electrolyzer_data')
    
    # Get token from environment
    influx_token = os.environ.get('INFLUXDB_ADMIN_TOKEN', '')
    
    if not influx_token:
        # Try loading from .env file
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
            timestamp_ns = sample['timestamp_ns']
            readings = sample['readings']
            
            point = Point("psu") \
                .tag("hardware", "psu") \
                .tag("location", "gen3_test_rig") \
                .field("voltage", float(readings['voltage'])) \
                .field("current", float(readings['current'])) \
                .field("power", float(readings['power'])) \
                .field("capacity", float(readings['capacity'])) \
                .field("runtime", int(readings['runtime'])) \
                .field("battery_v", float(readings['battery_v'])) \
                .field("temperature", int(readings['temperature'])) \
                .field("status", int(readings['status'])) \
                .field("set_voltage_rb", float(readings['set_voltage_rb'])) \
                .field("set_current_rb", float(readings['set_current_rb'])) \
                .field("output_enable", int(readings['output_enable'])) \
                .field("sys_fault", int(readings['sys_fault'])) \
                .field("mod_fault", int(readings['mod_fault'])) \
                .time(timestamp_ns, WritePrecision.NS)
            points.append(point)
        
        influx_write_api.write(bucket=influx_bucket, record=points)
        points_written += len(points)
        return True
    except Exception as e:
        print(f"[ERROR] InfluxDB write failed: {e}")
        return False


def read_psu_data():
    """Continuously read PSU data via Modbus RTU and write to InfluxDB"""
    global sample_buffer, device_online, SAMPLE_RATE, BUFFER_SECONDS
    
    config = load_config()
    psu_config = config['devices']['PSU']
    
    # Load bridge config
    bridge_config = config.get('bridges', {}).get('psu', {})
    SAMPLE_RATE = bridge_config.get('sample_rate', 8)
    BUFFER_SECONDS = bridge_config.get('buffer_seconds', 2)
    
    # Initialize ring buffer with max size
    max_samples = SAMPLE_RATE * BUFFER_SECONDS
    sample_buffer = deque(maxlen=max_samples)
    
    # Write batch size (write to InfluxDB every N samples)
    write_batch_size = SAMPLE_RATE  # Write every ~1 second
    pending_samples = []
    
    com_port = psu_config['com_port']
    if not com_port:
        print("[ERROR] COM port not configured in devices.yaml")
        print("  Set devices.PSU.com_port (e.g., 'COM11')")
        return
    
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Buffer size: {max_samples} samples ({BUFFER_SECONDS}s)")
    print(f"InfluxDB write batch: {write_batch_size} samples")
    
    while True:
        psu = None
        try:
            # Connect to PSU
            psu = minimalmodbus.Instrument(com_port, psu_config['slave_id'])
            psu.serial.baudrate = psu_config['baud_rate']
            psu.mode = minimalmodbus.MODE_RTU
            psu.serial.timeout = psu_config['timeout']
            psu.close_port_after_each_call = True  # Essential for USB adapters
            
            print(f"Attempting connection to PSU on {com_port}...")
            
            # Read loop with command processing
            while True:
                # Process pending commands
                while not command_queue.empty():
                    try:
                        cmd = command_queue.get_nowait()
                        cmd_type = cmd.get('type')
                        
                        if cmd_type == 'set_voltage_current':
                            voltage = cmd['voltage']
                            current = cmd['current']
                            psu.write_register(0x0101, int(voltage / 0.1))
                            time.sleep(0.1)
                            psu.write_register(0x0102, int(current / 0.1))
                            time.sleep(0.1)
                            psu.write_register(0x0103, cmd['enable'])
                            print(f"[OK] Set: {voltage:.1f}V, {current:.1f}A, {'ON' if cmd['enable'] else 'OFF'}")
                        
                        elif cmd_type == 'enable':
                            psu.write_register(0x0103, 1)
                            print("[OK] Output enabled")
                        
                        elif cmd_type == 'disable':
                            psu.write_register(0x0103, 0)
                            print("[OK] Output disabled")
                        
                        command_queue.task_done()
                    except Exception as e:
                        print(f"[ERROR] Command failed: {e}")
                
                # Read all 13 registers at once (0x0001-0x000D)
                raw_values = psu.read_registers(0x0001, 13)
                
                # Mark as online only after successful read
                if not device_online:
                    print(f"[OK] Connected to PSU on {com_port}")
                    device_online = True
                
                # Parse registers according to map
                readings = {
                    'voltage': raw_values[0] * 0.1,      # V
                    'current': raw_values[1] * 0.1,      # A
                    'power': raw_values[2] * 0.1,        # W
                    'capacity': raw_values[3] * 0.1,     # Ah
                    'runtime': raw_values[4],            # s
                    'battery_v': raw_values[5] * 0.1,    # V
                    'sys_fault': raw_values[6],          # fault code
                    'mod_fault': raw_values[7],          # fault code
                    'temperature': raw_values[8],        # C
                    'status': raw_values[9],             # status word
                    'set_voltage_rb': raw_values[10] * 0.1,  # V
                    'set_current_rb': raw_values[11] * 0.1,  # A
                    'output_enable': raw_values[12]      # 1=ON, 0=OFF
                }
                
                sample = {
                    'timestamp_ns': time.time_ns(),
                    'readings': readings
                }
                
                # Add to pending samples for InfluxDB write
                pending_samples.append(sample)
                
                # Also add to buffer for /metrics endpoint
                with data_lock:
                    sample_buffer.append(sample)
                
                # Write to InfluxDB when we have enough samples
                if len(pending_samples) >= write_batch_size:
                    write_to_influxdb(pending_samples)
                    pending_samples = []
                
                time.sleep(1.0 / SAMPLE_RATE)
        
        except Exception as e:
            device_online = False
            print(f"[ERROR] PSU offline: {e}")
            print(f"  Retrying in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)


@app.route('/metrics')
def metrics():
    """Return buffered metrics in InfluxDB line protocol format (for debugging)"""
    if not device_online:
        return Response("# Device offline\n", status=503, mimetype='text/plain')
    
    with data_lock:
        if sample_buffer is None or len(sample_buffer) == 0:
            return Response("# No data yet\n", status=503, mimetype='text/plain')
        
        samples = list(sample_buffer)
    
    lines = []
    for sample in samples:
        readings = sample['readings']
        timestamp_ns = sample['timestamp_ns']
        
        line = (f"psu "
                f"voltage={readings['voltage']:.2f},"
                f"current={readings['current']:.2f},"
                f"power={readings['power']:.2f},"
                f"capacity={readings['capacity']:.2f},"
                f"runtime={readings['runtime']},"
                f"battery_v={readings['battery_v']:.2f},"
                f"temperature={readings['temperature']},"
                f"status={readings['status']},"
                f"set_voltage_rb={readings['set_voltage_rb']:.2f},"
                f"set_current_rb={readings['set_current_rb']:.2f},"
                f"output_enable={readings['output_enable']},"
                f"sys_fault={readings['sys_fault']},"
                f"mod_fault={readings['mod_fault']} "
                f"{timestamp_ns}")
        lines.append(line)
    
    output = '\n'.join(lines) + '\n'
    return Response(output, mimetype='text/plain')


@app.route('/health')
def health():
    """Health check endpoint with buffer stats"""
    status = "online" if device_online else "offline"
    
    with data_lock:
        buffer_size = len(sample_buffer) if sample_buffer else 0
        buffer_max = sample_buffer.maxlen if sample_buffer else 0
    
    response = {
        'status': status,
        'device_online': device_online,
        'sample_rate': SAMPLE_RATE,
        'buffer_seconds': BUFFER_SECONDS,
        'buffer_size': buffer_size,
        'buffer_max': buffer_max,
        'buffer_pct': round(100 * buffer_size / buffer_max, 1) if buffer_max > 0 else 0,
        'influxdb_enabled': influx_write_api is not None,
        'points_written': points_written
    }
    
    import json
    return Response(json.dumps(response, indent=2), mimetype='application/json')


@app.route('/command', methods=['POST'])
def command():
    """Accept PSU control commands via HTTP POST"""
    if not device_online:
        return jsonify({'success': False, 'error': 'PSU offline'}), 503
    
    try:
        cmd_data = request.get_json()
        if not cmd_data:
            return jsonify({'success': False, 'error': 'No JSON data'}), 400
        
        command_queue.put(cmd_data)
        return jsonify({'success': True, 'message': 'Command queued'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def main():
    """Main entry point"""
    config = load_config()
    bridge_config = config.get('bridges', {}).get('psu', {})
    sample_rate = bridge_config.get('sample_rate', 8)
    hw_max = bridge_config.get('hw_max_rate', 10)
    
    print("PSU Modbus RTU HTTP Bridge (Direct InfluxDB)")
    print(f"Config: {CONFIG_PATH}")
    print(f"Configured rate: {sample_rate} Hz (hardware max: {hw_max} Hz)")
    print(f"Endpoints: http://localhost:8883/metrics, /health, /command")
    print()
    
    # Setup InfluxDB direct writes
    setup_influxdb()
    
    # Start reader thread
    reader_thread = threading.Thread(target=read_psu_data, daemon=True)
    reader_thread.start()
    
    # Start HTTP server
    app.run(host='0.0.0.0', port=8883, debug=False)


if __name__ == "__main__":
    main()
