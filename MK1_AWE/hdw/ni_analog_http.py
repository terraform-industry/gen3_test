#!/usr/bin/env python3
"""
NI cDAQ-9187 Analog Input HTTP Bridge
Reads 16 channels (4-20mA) from 2x NI-9253 modules and exposes via HTTP /metrics endpoint
Buffers samples at configured rate, dumps full buffer on /metrics request
"""

import nidaqmx
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

# Config values loaded at startup
SAMPLE_RATE = 100
BUFFER_SECONDS = 2


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
    """Continuously read analog inputs from NI cDAQ and buffer samples"""
    global sample_buffer, device_online, SAMPLE_RATE, BUFFER_SECONDS
    
    config = load_config()
    labels_config = yaml.safe_load(open(CONFIG_PATH.parent / "sensor_labels.yaml"))
    
    # Load bridge config
    bridge_config = config.get('bridges', {}).get('ni_analog', {})
    SAMPLE_RATE = bridge_config.get('sample_rate', 100)
    BUFFER_SECONDS = bridge_config.get('buffer_seconds', 2)
    
    # Initialize ring buffer with max size
    max_samples = SAMPLE_RATE * BUFFER_SECONDS
    sample_buffer = deque(maxlen=max_samples)
    
    device_name = config['devices']['NI_cDAQ']['name']
    slot1_config = config['modules']['NI_cDAQ_Analog']['slot_1']
    slot4_config = config['modules']['NI_cDAQ_Analog']['slot_4']
    ai_labels = labels_config.get('analog_inputs', {})
    
    # Calculate samples per read (10 reads per second for responsive buffer)
    samples_per_read = max(1, SAMPLE_RATE // 10)
    
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Samples per read: {samples_per_read}")
    print(f"Buffer size: {max_samples} samples ({BUFFER_SECONDS}s)")
    
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
                
                # Configure timing for continuous acquisition at configured rate
                task.timing.cfg_samp_clk_timing(
                    rate=SAMPLE_RATE,
                    sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS
                )
                
                # Set buffer to hold 1 second of data (prevents overflow)
                task.in_stream.input_buf_size = int(SAMPLE_RATE * 16 * 1)
                
                print(f"[OK] Connected to {device_name}")
                device_online = True
                
                # Read loop - batch read for efficiency
                while True:
                    # Read batch of samples from all channels
                    # Returns list of lists: [channel][sample]
                    data = task.read(number_of_samples_per_channel=samples_per_read)
                    
                    # Get base timestamp for this batch
                    now_ns = time.time_ns()
                    sample_interval_ns = int(1e9 / SAMPLE_RATE)
                    
                    # Process each sample in the batch
                    for sample_idx in range(samples_per_read):
                        # Calculate timestamp for this sample
                        # Samples are evenly spaced, work backwards from now
                        sample_offset = (samples_per_read - 1 - sample_idx) * sample_interval_ns
                        timestamp_ns = now_ns - sample_offset
                        
                        # Build readings for all channels
                        readings = {}
                        ch_idx = 0
                        
                        # Process Slot 1
                        for ch_name, hw_config in slot1_config.items():
                            current_ma = data[ch_idx][sample_idx] * 1000  # Convert A to mA
                            label_config = ai_labels.get(ch_name, {})
                            eng_value = convert_to_engineering_units(current_ma, hw_config, label_config)
                            readings[ch_name] = {
                                'value': eng_value,
                                'raw_ma': current_ma
                            }
                            ch_idx += 1
                        
                        # Process Slot 4
                        for ch_name, hw_config in slot4_config.items():
                            current_ma = data[ch_idx][sample_idx] * 1000
                            label_config = ai_labels.get(ch_name, {})
                            eng_value = convert_to_engineering_units(current_ma, hw_config, label_config)
                            readings[ch_name] = {
                                'value': eng_value,
                                'raw_ma': current_ma
                            }
                            ch_idx += 1
                        
                        # Add sample to buffer
                        with data_lock:
                            sample_buffer.append({
                                'timestamp_ns': timestamp_ns,
                                'readings': readings
                            })
        
        except Exception as e:
            device_online = False
            print(f"[ERROR] Device offline: {e}")
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
            # Format: measurement,tag=value field1=value1,field2=value2 timestamp
            line = f"ni_analog,channel={ch_name} value={data['value']:.3f},raw_ma={data['raw_ma']:.3f} {timestamp_ns}"
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
        'buffer_pct': round(100 * buffer_size / buffer_max, 1) if buffer_max > 0 else 0
    }
    
    import json
    return Response(json.dumps(response, indent=2), mimetype='application/json')


def main():
    """Main entry point"""
    config = load_config()
    bridge_config = config.get('bridges', {}).get('ni_analog', {})
    sample_rate = bridge_config.get('sample_rate', 100)
    hw_max = bridge_config.get('hw_max_rate', 2500)
    
    print("NI cDAQ Analog Input HTTP Bridge")
    print(f"Config: {CONFIG_PATH}")
    print(f"Configured rate: {sample_rate} Hz (hardware max: {hw_max} Hz)")
    print(f"Endpoints: http://localhost:8881/metrics, /health")
    print()
    
    # Start reader thread
    reader_thread = threading.Thread(target=read_analog_inputs, daemon=True)
    reader_thread.start()
    
    # Start HTTP server
    app.run(host='0.0.0.0', port=8881, debug=False)


if __name__ == "__main__":
    main()
