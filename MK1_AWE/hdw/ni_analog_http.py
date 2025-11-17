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
latest_relays = {}
device_online = False
data_lock = threading.Lock()


def load_config():
    """Load configuration from devices.yaml"""
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)
    return config


def convert_to_engineering_units(current_ma, channel_config):
    """Convert 4-20mA reading to engineering units"""
    range_min = channel_config['range_min'] * 1000  # Convert to mA
    range_max = channel_config['range_max'] * 1000
    eng_min = channel_config['eng_min']
    eng_max = channel_config['eng_max']
    
    # Clamp to valid range
    current_ma = max(range_min, min(range_max, current_ma))
    
    # Linear scaling
    eng_value = eng_min + (current_ma - range_min) * (eng_max - eng_min) / (range_max - range_min)
    return eng_value


def read_analog_inputs():
    """Continuously read analog inputs and relay states from NI cDAQ"""
    global latest_data, latest_relays, device_online
    
    config = load_config()
    device_name = config['devices']['NI_cDAQ']['name']
    slot1_config = config['modules']['NI_cDAQ_Analog']['slot_1']
    slot4_config = config['modules']['NI_cDAQ_Analog']['slot_4']
    slot2_relays = config['modules']['NI_cDAQ_Relays']['slot_2']
    slot3_relays = config['modules']['NI_cDAQ_Relays']['slot_3']
    
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
                    for ch_name, ch_config in slot1_config.items():
                        current_ma = data[idx] * 1000  # Convert A to mA
                        eng_value = convert_to_engineering_units(current_ma, ch_config)
                        readings[ch_name] = {
                            'value': eng_value,
                            'unit': ch_config['eng_unit'],
                            'raw_ma': current_ma
                        }
                        idx += 1
                    
                    # Process Slot 4
                    for ch_name, ch_config in slot4_config.items():
                        current_ma = data[idx] * 1000
                        eng_value = convert_to_engineering_units(current_ma, ch_config)
                        readings[ch_name] = {
                            'value': eng_value,
                            'unit': ch_config['eng_unit'],
                            'raw_ma': current_ma
                        }
                        idx += 1
                    
                    # Read relay states (separate task)
                    relay_states = {}
                    
                    # Read Slot 2 relays (RL01-RL08)
                    for relay_name, relay_config in slot2_relays.items():
                        ch_num = relay_config['channel']
                        try:
                            with nidaqmx.Task() as relay_task:
                                relay_task.di_channels.add_di_chan(f"{device_name}Mod2/port0/line{ch_num}")
                                state = relay_task.read()
                                relay_states[relay_name] = 1 if state else 0
                        except:
                            relay_states[relay_name] = 0
                    
                    # Read Slot 3 relays (RL09-RL16)
                    for relay_name, relay_config in slot3_relays.items():
                        ch_num = relay_config['channel']
                        try:
                            with nidaqmx.Task() as relay_task:
                                relay_task.di_channels.add_di_chan(f"{device_name}Mod3/port0/line{ch_num}")
                                state = relay_task.read()
                                relay_states[relay_name] = 1 if state else 0
                        except:
                            relay_states[relay_name] = 0
                    
                    # Update global state
                    with data_lock:
                        latest_data['timestamp'] = time.time()
                        latest_data['readings'] = readings
                        latest_relays['states'] = relay_states
                    
                    time.sleep(1.0 / SAMPLE_RATE)
        
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
        relay_states = latest_relays.get('states', {})
        timestamp = latest_data['timestamp']
    
    # Build InfluxDB line protocol
    lines = []
    
    # Analog input metrics
    for ch_name, data in readings.items():
        # Format: measurement,tag1=value1 field1=value1,field2=value2 timestamp
        line = f"ni_analog,channel={ch_name} value={data['value']:.3f},raw_ma={data['raw_ma']:.3f} {int(timestamp * 1e9)}"
        lines.append(line)
    
    # Relay state metrics (single line with all relays)
    if relay_states:
        relay_fields = ','.join([f"{name}={state}i" for name, state in sorted(relay_states.items())])
        relay_line = f"ni_relays {relay_fields} {int(timestamp * 1e9)}"
        lines.append(relay_line)
    
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

