#!/usr/bin/env python3
"""
NI cDAQ-9187 Analog Input HTTP Bridge
Reads 16 channels (4-20mA) from 2x NI-9253 modules and exposes via HTTP /metrics endpoint
"""

import nidaqmx
import yaml
import time
import threading
from flask import Flask, Response
from pathlib import Path

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
SAMPLE_RATE = 10  # Hz per channel
RECONNECT_DELAY = 5  # seconds

app = Flask(__name__)

# Global state
latest_data = {}
device_online = False
data_lock = threading.Lock()


def load_config():
    """Load configuration from devices.yaml"""
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)
    return config


def convert_to_engineering_units(current_ma, hw_config, label_config):
    """Convert 4-20mA reading to engineering units"""
    range_min = hw_config['range_min'] * 1000  # Convert to mA
    range_max = hw_config['range_max'] * 1000
    eng_min = label_config.get('eng_min', 0.0)
    eng_max = label_config.get('eng_max', 100.0)
    
    # Clamp to valid range
    current_ma = max(range_min, min(range_max, current_ma))
    
    # Linear scaling
    eng_value = eng_min + (current_ma - range_min) * (eng_max - eng_min) / (range_max - range_min)
    return eng_value


def read_analog_inputs():
    """Continuously read analog inputs from NI cDAQ"""
    global latest_data, device_online
    
    config = load_config()
    labels_config = yaml.safe_load(open(CONFIG_PATH.parent / "sensor_labels.yaml"))
    
    device_name = config['devices']['NI_cDAQ']['name']
    slot1_config = config['modules']['NI_cDAQ_Analog']['slot_1']
    slot4_config = config['modules']['NI_cDAQ_Analog']['slot_4']
    ai_labels = labels_config.get('analog_inputs', {})
    
    while True:
        try:
            # Create task
            with nidaqmx.Task() as task:
                # Add channels from Slot 1 (AI01-AI08)
                for ch_name, ch_config in slot1_config.items():
                    ch_num = ch_config['channel']
                    task.ai_channels.add_ai_current_chan(
                        f"{device_name}Mod1/ai{ch_num}",
                        min_val=-0.020,
                        max_val=0.020,
                        name_to_assign_to_channel=ch_name
                    )
                
                # Add channels from Slot 4 (AI09-AI16)
                for ch_name, ch_config in slot4_config.items():
                    ch_num = ch_config['channel']
                    task.ai_channels.add_ai_current_chan(
                        f"{device_name}Mod4/ai{ch_num}",
                        min_val=-0.020,
                        max_val=0.020,
                        name_to_assign_to_channel=ch_name
                    )
                
                # Configure timing
                task.timing.cfg_samp_clk_timing(
                    rate=SAMPLE_RATE,
                    sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS
                )
                
                # Minimal buffer - only 0.5 seconds worth
                task.in_stream.input_buf_size = int(SAMPLE_RATE * 16 * 0.5)
                
                print(f"✓ Connected to {device_name}")
                device_online = True
                
                # Read loop
                while True:
                    # Read one sample from all channels
                    data = task.read()
                    
                    # Convert to engineering units
                    readings = {}
                    idx = 0
                    
                    # Process Slot 1
                    for ch_name, hw_config in slot1_config.items():
                        current_ma = data[idx] * 1000  # Convert A to mA
                        label_config = ai_labels.get(ch_name, {})
                        eng_value = convert_to_engineering_units(current_ma, hw_config, label_config)
                        readings[ch_name] = {
                            'value': eng_value,
                            'unit': label_config.get('eng_unit', 'units'),
                            'raw_ma': current_ma
                        }
                        idx += 1
                    
                    # Process Slot 4
                    for ch_name, hw_config in slot4_config.items():
                        current_ma = data[idx] * 1000
                        label_config = ai_labels.get(ch_name, {})
                        eng_value = convert_to_engineering_units(current_ma, hw_config, label_config)
                        readings[ch_name] = {
                            'value': eng_value,
                            'unit': label_config.get('eng_unit', 'units'),
                            'raw_ma': current_ma
                        }
                        idx += 1
                    
                    # Update global state
                    with data_lock:
                        latest_data['timestamp'] = time.time()
                        latest_data['readings'] = readings
                    
                    # Short sleep to prevent CPU spinning (sample at ~10Hz)
                    time.sleep(0.05)
        
        except Exception as e:
            device_online = False
            print(f"✗ Device offline: {e}")
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
    
    # Build InfluxDB line protocol (analog inputs only)
    lines = []
    for ch_name, data in readings.items():
        # Format: measurement,tag1=value1 field1=value1,field2=value2 timestamp
        line = f"ni_analog,channel={ch_name} value={data['value']:.3f},raw_ma={data['raw_ma']:.3f} {int(timestamp * 1e9)}"
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


def main():
    """Main entry point"""
    print("NI cDAQ Analog Input HTTP Bridge")
    print(f"Config: {CONFIG_PATH}")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Endpoints: http://localhost:8881/metrics, /health")
    print()
    
    # Start reader thread
    reader_thread = threading.Thread(target=read_analog_inputs, daemon=True)
    reader_thread.start()
    
    # Start HTTP server
    app.run(host='0.0.0.0', port=8881, debug=False)


if __name__ == "__main__":
    main()

