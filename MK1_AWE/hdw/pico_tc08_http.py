#!/usr/bin/env python3
"""
Pico TC-08 Thermocouple HTTP Bridge
Reads 8 thermocouple channels and exposes via HTTP /metrics endpoint
Buffers samples at configured rate, dumps full buffer on /metrics request
"""

import ctypes
import yaml
import time
import threading
from collections import deque
from flask import Flask, Response
from pathlib import Path

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
RECONNECT_DELAY = 5  # seconds

app = Flask(__name__)

# Global state
sample_buffer = None  # Will be initialized as deque
device_online = False
data_lock = threading.Lock()
tc08 = None

# Config values loaded at startup
SAMPLE_RATE = 1
BUFFER_SECONDS = 2


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
    """Continuously read thermocouples from Pico TC-08 and buffer samples"""
    global sample_buffer, device_online, tc08, SAMPLE_RATE, BUFFER_SECONDS
    
    config = load_config()
    dll_path = config['devices']['Pico_TC08']['dll_path']
    channels_config = config['modules']['Pico_TC08_Channels']
    
    # Load bridge config
    bridge_config = config.get('bridges', {}).get('pico_tc08', {})
    SAMPLE_RATE = bridge_config.get('sample_rate', 1)
    BUFFER_SECONDS = bridge_config.get('buffer_seconds', 2)
    
    # Initialize ring buffer with max size
    max_samples = SAMPLE_RATE * BUFFER_SECONDS
    sample_buffer = deque(maxlen=max_samples)
    
    # Calculate sample interval in ms (hardware minimum is 1000ms)
    sample_interval_ms = max(1000, int(1000 / SAMPLE_RATE))
    
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Buffer size: {max_samples} samples ({BUFFER_SECONDS}s)")
    
    tc08 = setup_dll(dll_path)
    
    while True:
        handle = None
        try:
            # Open device
            handle = tc08.usb_tc08_open_unit()
            if handle <= 0:
                raise RuntimeError("TC-08 not found")
            
            print(f"[OK] Connected to Pico TC-08 (handle={handle})")
            
            # Configure cold junction (channel 0)
            tc08.usb_tc08_set_channel(handle, 0, ctypes.c_char(b'C'))
            
            # Configure thermocouple channels
            for ch_name, ch_config in channels_config.items():
                ch_num = ch_config['channel']
                tc_type = ch_config['type'].encode('ascii')
                tc08.usb_tc08_set_channel(handle, ch_num, ctypes.c_char(tc_type))
            
            # Start streaming
            actual_interval = tc08.usb_tc08_run(handle, sample_interval_ms)
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
                            'type': ch_config['type'],
                            'valid': True
                        }
                    else:
                        readings[ch_name] = {
                            'value': None,
                            'type': ch_config['type'],
                            'valid': False
                        }
                
                # Add sample to buffer
                with data_lock:
                    sample_buffer.append({
                        'timestamp_ns': time.time_ns(),
                        'readings': readings
                    })
                
                time.sleep(sample_interval_ms / 1000.0)
        
        except Exception as e:
            device_online = False
            print(f"[ERROR] Device offline: {e}")
            
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
    """Return all buffered metrics in InfluxDB line protocol format, then clear buffer"""
    if not device_online:
        return Response("# Device offline\n", status=503, mimetype='text/plain')
    
    with data_lock:
        if sample_buffer is None or len(sample_buffer) == 0:
            return Response("# No data yet\n", status=503, mimetype='text/plain')
        
        # Grab all buffered samples and clear
        samples = list(sample_buffer)
        sample_buffer.clear()
    
    # Build InfluxDB line protocol - one line per channel per sample
    lines = []
    for sample in samples:
        timestamp_ns = sample['timestamp_ns']
        for ch_name, data in sample['readings'].items():
            if data['valid']:
                # Format: measurement,tag1=value1 field1=value1 timestamp
                line = f"tc08,channel={ch_name},type={data['type']} temp_c={data['value']:.2f} {timestamp_ns}"
                lines.append(line)
    
    output = '\n'.join(lines) + '\n' if lines else "# No valid readings\n"
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
        'buffer_pct': round(100 * buffer_size / buffer_max, 1) if buffer_max > 0 else 0
    }
    
    import json
    return Response(json.dumps(response, indent=2), mimetype='application/json')


def main():
    """Main entry point"""
    config = load_config()
    bridge_config = config.get('bridges', {}).get('pico_tc08', {})
    sample_rate = bridge_config.get('sample_rate', 1)
    hw_max = bridge_config.get('hw_max_rate', 1)
    
    print("Pico TC-08 Thermocouple HTTP Bridge")
    print(f"Config: {CONFIG_PATH}")
    print(f"Configured rate: {sample_rate} Hz (hardware max: {hw_max} Hz)")
    print(f"Endpoints: http://localhost:8882/metrics, /health")
    print()
    
    # Start reader thread
    reader_thread = threading.Thread(target=read_thermocouples, daemon=True)
    reader_thread.start()
    
    # Start HTTP server
    app.run(host='0.0.0.0', port=8882, debug=False)


if __name__ == "__main__":
    main()
