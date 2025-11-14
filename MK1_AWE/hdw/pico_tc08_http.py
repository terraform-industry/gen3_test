#!/usr/bin/env python3
"""
Pico TC-08 Thermocouple HTTP Bridge
Reads 8 thermocouple channels and exposes via HTTP /metrics endpoint
"""

import ctypes
import yaml
import time
import threading
from flask import Flask, Response
from pathlib import Path

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
SAMPLE_INTERVAL_MS = 1000  # 1Hz (hardware limitation)
RECONNECT_DELAY = 5  # seconds

app = Flask(__name__)

# Global state
latest_data = {}
device_online = False
data_lock = threading.Lock()
tc08 = None


def load_config():
    """Load configuration from devices.yaml"""
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)
    return config


def setup_dll(dll_path):
    """Setup ctypes prototypes for Pico TC-08 DLL"""
    dll = ctypes.WinDLL(dll_path)
    
    # Function prototypes
    dll.usb_tc08_open_unit.restype = ctypes.c_int16
    
    dll.usb_tc08_set_channel.argtypes = [
        ctypes.c_int16,    # handle
        ctypes.c_int16,    # channel
        ctypes.c_char      # type char
    ]
    dll.usb_tc08_set_channel.restype = ctypes.c_int16
    
    dll.usb_tc08_run.argtypes = [
        ctypes.c_int16,    # handle
        ctypes.c_int32     # interval (ms)
    ]
    dll.usb_tc08_run.restype = ctypes.c_int32
    
    dll.usb_tc08_get_temp.argtypes = [
        ctypes.c_int16,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.c_int16,
        ctypes.c_int16,
        ctypes.c_int16
    ]
    dll.usb_tc08_get_temp.restype = ctypes.c_int32
    
    dll.usb_tc08_stop.argtypes = [ctypes.c_int16]
    dll.usb_tc08_stop.restype = ctypes.c_int16
    
    dll.usb_tc08_close_unit.argtypes = [ctypes.c_int16]
    dll.usb_tc08_close_unit.restype = ctypes.c_int16
    
    return dll


def read_thermocouples():
    """Continuously read thermocouples from Pico TC-08"""
    global latest_data, device_online, tc08
    
    config = load_config()
    dll_path = config['devices']['Pico_TC08']['dll_path']
    channels_config = config['modules']['Pico_TC08_Channels']
    
    tc08 = setup_dll(dll_path)
    
    while True:
        handle = None
        try:
            # Open device
            handle = tc08.usb_tc08_open_unit()
            if handle <= 0:
                raise RuntimeError("TC-08 not found")
            
            print(f"✓ Connected to Pico TC-08 (handle={handle})")
            
            # Configure cold junction (channel 0)
            tc08.usb_tc08_set_channel(handle, 0, ctypes.c_char(b'C'))
            
            # Configure thermocouple channels
            for ch_name, ch_config in channels_config.items():
                ch_num = ch_config['channel']
                tc_type = ch_config['type'].encode('ascii')
                tc08.usb_tc08_set_channel(handle, ch_num, ctypes.c_char(tc_type))
            
            # Start streaming
            actual_interval = tc08.usb_tc08_run(handle, SAMPLE_INTERVAL_MS)
            if actual_interval <= 0:
                raise RuntimeError("Failed to start streaming")
            
            print(f"  Sampling at {actual_interval} ms intervals")
            device_online = True
            
            # Read loop
            while True:
                readings = {}
                overflow = ctypes.c_int16(0)
                
                for ch_name, ch_config in channels_config.items():
                    ch_num = ch_config['channel']
                    
                    # Prepare buffers
                    temp_buffer = (ctypes.c_float * 1)()
                    time_buffer = (ctypes.c_int32 * 1)()
                    
                    # Read temperature
                    result = tc08.usb_tc08_get_temp(
                        handle,
                        temp_buffer,
                        time_buffer,
                        1,  # one reading
                        ctypes.byref(overflow),
                        ctypes.c_int16(ch_num),
                        ctypes.c_int16(0),  # 0 = Celsius
                        ctypes.c_int16(0)   # no trigger
                    )
                    
                    temp_c = temp_buffer[0]
                    
                    # Filter invalid readings
                    # TC-08 returns large negative values for open/failed thermocouples
                    if -200 < temp_c < 1500:  # Valid range for K-type
                        readings[ch_name] = {
                            'value': temp_c,
                            'unit': '°C',
                            'type': ch_config['type'],
                            'valid': True
                        }
                    else:
                        readings[ch_name] = {
                            'value': None,
                            'unit': '°C',
                            'type': ch_config['type'],
                            'valid': False
                        }
                
                # Update global state
                with data_lock:
                    latest_data['timestamp'] = time.time()
                    latest_data['readings'] = readings
                
                time.sleep(SAMPLE_INTERVAL_MS / 1000.0)
        
        except Exception as e:
            device_online = False
            print(f"✗ Device offline: {e}")
            
            # Clean up
            if handle and handle > 0:
                try:
                    tc08.usb_tc08_stop(handle)
                    tc08.usb_tc08_close_unit(handle)
                except:
                    pass
            
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
    for ch_name, data in readings.items():
        if data['valid']:
            # Format: measurement,tag1=value1 field1=value1 timestamp
            line = f"tc08,channel={ch_name},type={data['type']} temp_c={data['value']:.2f} {int(timestamp * 1e9)}"
            lines.append(line)
    
    output = '\n'.join(lines) + '\n' if lines else "# No valid readings\n"
    return Response(output, mimetype='text/plain')


@app.route('/health')
def health():
    """Health check endpoint"""
    status = "online" if device_online else "offline"
    
    with data_lock:
        data_age = time.time() - latest_data.get('timestamp', 0) if latest_data else None
        num_valid = sum(1 for r in latest_data.get('readings', {}).values() if r.get('valid', False))
        num_total = len(latest_data.get('readings', {}))
    
    response = {
        'status': status,
        'device_online': device_online,
        'data_age_seconds': data_age,
        'valid_channels': num_valid,
        'total_channels': num_total,
        'sample_interval_ms': SAMPLE_INTERVAL_MS
    }
    
    import json
    return Response(json.dumps(response, indent=2), mimetype='application/json')


def main():
    """Main entry point"""
    print("Pico TC-08 Thermocouple HTTP Bridge")
    print(f"Config: {CONFIG_PATH}")
    print(f"Sample interval: {SAMPLE_INTERVAL_MS} ms (1 Hz)")
    print(f"Endpoints: http://localhost:8882/metrics, /health")
    print()
    
    # Start reader thread
    reader_thread = threading.Thread(target=read_thermocouples, daemon=True)
    reader_thread.start()
    
    # Start HTTP server
    app.run(host='0.0.0.0', port=8882, debug=False)


if __name__ == "__main__":
    main()

