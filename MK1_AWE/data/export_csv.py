#!/usr/bin/env python3
"""Export Gen3 AWE InfluxDB data to CSV. Configuration in test_config.py"""

from influxdb_client import InfluxDBClient
from datetime import datetime
from pathlib import Path
import sys
import os
import warnings
import traceback
from influxdb_client.client.warnings import MissingPivotFunction

# Suppress influxdb_client warnings about pivot function
warnings.simplefilter("ignore", MissingPivotFunction)

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use environment variables

# Import configuration from single source of truth
from test_config import (
    TEST_NAME, START_TIME, STOP_TIME, START_TIME_UTC, STOP_TIME_UTC,
    DOWNSAMPLE_AIX, DOWNSAMPLE_TC, DOWNSAMPLE_PSU, DOWNSAMPLE_BGA, DOWNSAMPLE_RL,
    DOWNSAMPLE_FUNCTION
)
import pandas as pd

# InfluxDB Connection (reads from parent config/devices.yaml)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'gui'))
from config_loader import get_influx_params, load_sensor_labels


# Removed convert_mA_to_eng - not needed for raw data export


def export_sensor_group(client, influx_params, output_dir, date_str, 
                        measurement, channels, downsample_window, filename_suffix, 
                        field_name=None, use_channel_tag=False, use_labels=False):
    """Export a group of related sensors to a single CSV
    
    Args:
        measurement: InfluxDB measurement name
        channels: List of channel names
        field_name: Field to extract (if using channel tags), e.g., 'raw_ma', 'temp_c'
        use_channel_tag: If True, filter by channel tag instead of field name
        use_labels: If True, rename columns using sensor_labels.yaml
    """
    
    if use_channel_tag and field_name:
        # For measurements like ni_analog, tc08 that use channel tags
        channel_filter = ' or '.join([f'r.channel == "{ch}"' for ch in channels])
        query = f'''
from(bucket: "{influx_params['bucket']}")
  |> range(start: {START_TIME_UTC}, stop: {STOP_TIME_UTC})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "{field_name}")
  |> filter(fn: (r) => {channel_filter})
  |> aggregateWindow(every: {downsample_window}, fn: {DOWNSAMPLE_FUNCTION}, createEmpty: false)
  |> pivot(rowKey:["_time"], columnKey: ["channel"], valueColumn: "_value")
'''
    else:
        # For measurements like ni_relays, psu that use field names directly
        field_filter = ' or '.join([f'r._field == "{f}"' for f in channels])
        query = f'''
from(bucket: "{influx_params['bucket']}")
  |> range(start: {START_TIME_UTC}, stop: {STOP_TIME_UTC})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => {field_filter})
  |> aggregateWindow(every: {downsample_window}, fn: {DOWNSAMPLE_FUNCTION}, createEmpty: false)
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
'''
    
    print(f"\nExporting {filename_suffix}...")
    
    try:
        df = client.query_api().query_data_frame(query)
        
        if df.empty:
            print(f"  [!] No data found")
            return None
        
        # Keep only timestamp and data columns
        keep_cols = ['_time'] + [col for col in df.columns if col in channels]
        df = df[keep_cols]
        
        # Convert timestamps from UTC to local timezone and format as string
        df['_time'] = df['_time'].dt.tz_convert('America/Los_Angeles')
        df['_time'] = df['_time'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
        df.rename(columns={'_time': 'timestamp'}, inplace=True)
        
        # Rename columns using sensor labels if requested
        if use_labels:
            labels = load_sensor_labels()
            
            # Build rename mapping
            rename_map = {}
            for col in df.columns:
                if col == 'timestamp':
                    continue
                
                # Try different label sources
                if col in labels.get('analog_inputs', {}):
                    label_config = labels['analog_inputs'][col]
                    rename_map[col] = label_config.get('label', col) if isinstance(label_config, dict) else label_config
                elif col in labels.get('thermocouples', {}):
                    rename_map[col] = labels['thermocouples'][col]
                elif col in labels.get('bgas', {}):
                    label_config = labels['bgas'][col]
                    rename_map[col] = label_config.get('label', col) if isinstance(label_config, dict) else label_config
            
            if rename_map:
                df.rename(columns=rename_map, inplace=True)
        
        # Save to CSV with proper float formatting
        output_file = f"{date_str}_{filename_suffix}.csv"
        output_path = os.path.join(output_dir, output_file)
        df.to_csv(output_path, index=False, float_format='%.6f')
        
        print(f"  [OK] {len(df)} points, {len(keep_cols)-1} channels")
        print(f"       File: {output_file} ({os.path.getsize(output_path) / 1024:.1f} KB)")
        
        return df
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None


# Removed export_converted_sensors - Gen3 exports raw data only


def export_bga_data(client, influx_params, output_dir, date_str, downsample_window):
    """Export BGA data with multiple fields per device"""
    
    print(f"\nExporting BGA data...")
    
    # Load labels for BGA naming
    labels = load_sensor_labels()
    bga_labels = labels.get('bgas', {})
    
    try:
        # Export each BGA separately to avoid duplicate rows
        for bga_id in ['BGA01', 'BGA02', 'BGA03']:
            query = f'''
from(bucket: "{influx_params['bucket']}")
  |> range(start: {START_TIME_UTC}, stop: {STOP_TIME_UTC})
  |> filter(fn: (r) => r._measurement == "bga_metrics")
  |> filter(fn: (r) => r.bga_id == "{bga_id}")
  |> filter(fn: (r) => r._field == "purity" or 
                       r._field == "uncertainty" or
                       r._field == "temperature" or
                       r._field == "pressure")
  |> aggregateWindow(every: {downsample_window}, fn: {DOWNSAMPLE_FUNCTION}, createEmpty: false)
  |> keep(columns: ["_time", "_field", "_value", "primary_gas", "secondary_gas"])
'''
            
            df = client.query_api().query_data_frame(query)
            
            if df.empty:
                print(f"  [!] {bga_id}: No data found")
                continue
            
            # Pivot manually using pandas (more reliable than Flux pivot with tags)
            df_pivot = df.pivot_table(
                index='_time',
                columns='_field',
                values='_value',
                aggfunc='first'  # Take first value if duplicates
            ).reset_index()
            
            # Add gas info from the original df (take most common value per timestamp)
            if 'primary_gas' in df.columns and 'secondary_gas' in df.columns:
                gas_info = df.groupby('_time')[['primary_gas', 'secondary_gas']].first().reset_index()
                df_pivot = df_pivot.merge(gas_info, on='_time', how='left')
            
            # Convert timestamps from UTC to local timezone and format as string
            df_pivot['_time'] = df_pivot['_time'].dt.tz_convert('America/Los_Angeles')
            df_pivot['_time'] = df_pivot['_time'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
            df_pivot.rename(columns={'_time': 'timestamp'}, inplace=True)
            
            # Save to CSV with proper float formatting (use label in filename if available)
            bga_label_config = bga_labels.get(bga_id, {})
            bga_label = bga_label_config.get('label', bga_id) if isinstance(bga_label_config, dict) else bga_id
            output_file = f"{date_str}_BGA_{bga_label.replace(' ', '_')}.csv"
            output_path = os.path.join(output_dir, output_file)
            df_pivot.to_csv(output_path, index=False, float_format='%.6f')
            
            print(f"  [OK] {bga_id}: {len(df_pivot)} points")
            print(f"       File: {output_file} ({os.path.getsize(output_path) / 1024:.1f} KB)")
            
    except Exception as e:
        print(f"  [ERROR] {e}")


def export_data():
    """Export all Gen3 sensor data with configured parameters"""
    
    # Use local time for folder naming
    date_str = START_TIME.strftime('%Y-%m-%d')
    
    # Create output directory: YYYY-MM-DD_TEST_NAME/csv/
    test_dir = os.path.join(os.path.dirname(__file__), f"{date_str}_{TEST_NAME}")
    output_dir = os.path.join(test_dir, 'csv')
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"=" * 60)
    print(f"Gen3 AWE Data Export")
    print(f"=" * 60)
    print(f"Test: {TEST_NAME}")
    print(f"Time range: {START_TIME.strftime('%Y-%m-%d %H:%M:%S %Z')} to {STOP_TIME.strftime('%H:%M:%S %Z')}")
    print(f"Output directory: {os.path.basename(test_dir)}/csv/")
    
    # Get InfluxDB credentials
    influx_params = get_influx_params()
    
    # For token, check environment
    token = os.getenv('INFLUXDB_ADMIN_TOKEN')
    if not token:
        print("\nError: INFLUXDB_ADMIN_TOKEN environment variable not set")
        print("Set it in PowerShell:")
        print('  $env:INFLUXDB_ADMIN_TOKEN="your_token_here"')
        sys.exit(1)
    
    # Connect to InfluxDB
    client = InfluxDBClient(
        url=influx_params['url'],
        token=token,
        org=influx_params['org']
    )
    
    try:
        # Export analog inputs (AI01-AI16) - raw mA values from ni_analog measurement
        ai_channels = [f"AI{i:02d}" for i in range(1, 17)]
        export_sensor_group(client, influx_params, output_dir, date_str,
                          "ni_analog", ai_channels, DOWNSAMPLE_AIX, "AIX",
                          field_name="raw_ma", use_channel_tag=True)
        
        # Export analog inputs (AI01-AI16) - converted engineering units
        export_sensor_group(client, influx_params, output_dir, date_str,
                          "ni_analog", ai_channels, DOWNSAMPLE_AIX, "AIX_converted",
                          field_name="value", use_channel_tag=True, use_labels=True)
        
        # Export thermocouples (TC01-TC08) from tc08 measurement
        tc_channels = [f"TC{i:02d}" for i in range(1, 9)]
        export_sensor_group(client, influx_params, output_dir, date_str,
                          "tc08", tc_channels, DOWNSAMPLE_TC, "TC",
                          field_name="temp_c", use_channel_tag=True, use_labels=True)
        
        # Export relays (RL01-RL16) from ni_relays measurement
        rl_fields = [f"RL{i:02d}" for i in range(1, 17)]
        export_sensor_group(client, influx_params, output_dir, date_str,
                          "ni_relays", rl_fields, DOWNSAMPLE_RL, "RL",
                          use_channel_tag=False)
        
        # Export PSU data (all fields in single CSV)
        psu_fields = ["voltage", "current", "power", "capacity", "runtime", 
                      "battery_v", "temperature", "status", "sys_fault", "mod_fault",
                      "set_voltage_rb", "set_current_rb", "output_enable"]
        export_sensor_group(client, influx_params, output_dir, date_str,
                          "psu", psu_fields, DOWNSAMPLE_PSU, "PSU",
                          use_channel_tag=False)
        
        # Export BGA data (separate per device)
        export_bga_data(client, influx_params, output_dir, date_str, DOWNSAMPLE_BGA)
        
        print(f"\n{'=' * 60}")
        print(f"[OK] Export complete: {test_dir}")
        print(f"{'=' * 60}")
        print(f"\nExported files:")
        print(f"  - {date_str}_AIX.csv (16 analog inputs, raw mA)")
        print(f"  - {date_str}_AIX_converted.csv (16 analog inputs, engineering units)")
        print(f"  - {date_str}_TC.csv (8 thermocouples, C)")
        print(f"  - {date_str}_RL.csv (16 relay states, 1/0)")
        print(f"  - {date_str}_PSU.csv (PSU data)")
        print(f"  - {date_str}_BGA_BGA01/02/03.csv (BGA data)")
        
    except Exception as e:
        print(f"\nError: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    export_data()
