#!/usr/bin/env python3
"""
PSU Modbus RTU HTTP Bridge
Reads PSU data via RS485/USB and exposes via HTTP /metrics endpoint
"""

import minimalmodbus
import yaml
import time
import threading
import queue
from flask import Flask, Response, request, jsonify
from pathlib import Path

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
SAMPLE_RATE = 10  # Hz
RECONNECT_DELAY = 5  # seconds

app = Flask(__name__)

# Global state
latest_data = {}
device_online = False
data_lock = threading.Lock()
command_queue = queue.Queue()


def load_config():
    """Load configuration from devices.yaml"""
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)
    return config


def read_psu_data():
    """Continuously read PSU data via Modbus RTU"""
    global latest_data, device_online
    
    config = load_config()
    psu_config = config['devices']['PSU']
    register_map = config['modules']['PSU_Registers']
    
    com_port = psu_config['com_port']
    if not com_port:
        print("✗ COM port not configured in devices.yaml")
        print("  Set devices.PSU.com_port (e.g., 'COM11')")
        return
    
    while True:
        psu = None
        try:
            # Connect to PSU
            psu = minimalmodbus.Instrument(com_port, psu_config['slave_id'])
            psu.serial.baudrate = psu_config['baud_rate']
            psu.mode = minimalmodbus.MODE_RTU
            psu.serial.timeout = psu_config['timeout']
            psu.close_port_after_each_call = True  # Essential for USB adapters
            
            print(f"✓ Connected to PSU on {com_port}")
            device_online = True
            
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
                            print(f"✓ Set: {voltage:.1f}V, {current:.1f}A, {'ON' if cmd['enable'] else 'OFF'}")
                        
                        elif cmd_type == 'enable':
                            psu.write_register(0x0103, 1)
                            print("✓ Output enabled")
                        
                        elif cmd_type == 'disable':
                            psu.write_register(0x0103, 0)
                            print("✓ Output disabled")
                        
                        command_queue.task_done()
                    except Exception as e:
                        print(f"✗ Command failed: {e}")
                
                # Read all 13 registers at once (0x0001-0x000D)
                raw_values = psu.read_registers(0x0001, 13)
                
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
                
                # Update global state
                with data_lock:
                    latest_data['timestamp'] = time.time()
                    latest_data['readings'] = readings
                
                time.sleep(1.0 / SAMPLE_RATE)
        
        except Exception as e:
            device_online = False
            print(f"✗ PSU offline: {e}")
            print(f"  Retrying in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)


@app.route('/metrics')
def metrics():
    """Return metrics in InfluxDB line protocol format"""
    if not device_online:
        return Response("# Device offline\n", status=503, mimetype='text/plain')
    
    with data_lock:
        if 'readings' not in latest_data:
            return Response("# No data yet\n", status=503, mimetype='text/plain')
        
        readings = latest_data['readings']
        timestamp = latest_data['timestamp']
    
    # Build InfluxDB line protocol
    lines = []
    
    # Main measurements (voltage, current, power)
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
            f"{int(timestamp * 1e9)}")
    lines.append(line)
    
    output = '\n'.join(lines) + '\n'
    return Response(output, mimetype='text/plain')


@app.route('/health')
def health():
    """Health check endpoint"""
    status = "online" if device_online else "offline"
    with data_lock:
        data_age = time.time() - latest_data.get('timestamp', 0) if latest_data else None
    
    response = {
        'status': status,
        'device_online': device_online,
        'data_age_seconds': data_age,
        'sample_rate': SAMPLE_RATE
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
        
        # Queue command for execution in read loop
        command_queue.put(cmd_data)
        
        return jsonify({'success': True, 'message': 'Command queued'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def main():
    """Main entry point"""
    print("PSU Modbus RTU HTTP Bridge")
    print(f"Config: {CONFIG_PATH}")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Endpoints: http://localhost:8883/metrics, /health")
    print()
    
    # Start reader thread
    reader_thread = threading.Thread(target=read_psu_data, daemon=True)
    reader_thread.start()
    
    # Start HTTP server
    app.run(host='0.0.0.0', port=8883, debug=False)


if __name__ == "__main__":
    main()

