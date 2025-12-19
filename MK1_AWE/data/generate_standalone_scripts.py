#!/usr/bin/env python3
"""
Generate standalone export and plotting scripts for the export folder.

These scripts are self-contained and can regenerate CSVs/plots without
needing the full MK1_AWE codebase.
"""

from datetime import datetime
from pathlib import Path
import sys
import os

# Add path to import config_loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'gui'))
from config_loader import load_sensor_labels, get_influx_params


def generate_standalone_export_csv(
    test_name: str,
    start_time: datetime,
    stop_time: datetime,
    max_export_rate_hz: int = 10
) -> str:
    """Generate a standalone export_csv.py script with hardcoded parameters.
    
    Returns:
        Python script as a string
    """
    
    # Load current config to embed
    sensor_labels = load_sensor_labels()
    influx_params = get_influx_params()
    
    # Format times
    start_str = start_time.isoformat()
    stop_str = stop_time.isoformat()
    tz_name = str(start_time.tzinfo)
    downsample_window = f"{int(1000 / max_export_rate_hz)}ms"
    
    # Build sensor labels dict as Python literal
    def dict_to_python(d, indent=0):
        """Convert dict to Python literal string."""
        lines = ["{"]
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{'    ' * (indent+1)}'{k}': {dict_to_python(v, indent+1)},")
            elif isinstance(v, str):
                lines.append(f"{'    ' * (indent+1)}'{k}': '{v}',")
            else:
                lines.append(f"{'    ' * (indent+1)}'{k}': {v},")
        lines.append(f"{'    ' * indent}}}")
        return '\n'.join(lines)
    
    sensor_labels_str = dict_to_python(sensor_labels, indent=0)
    
    script = f'''#!/usr/bin/env python3
"""
Standalone CSV Export Script - {test_name}

This script regenerates the CSV files from InfluxDB.
Run from the export folder: python export_csv.py

Requirements:
  - influxdb-client
  - pandas
  - python-dotenv (optional)

Environment:
  - INFLUXDB_ADMIN_TOKEN: Set this environment variable with your token

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

from influxdb_client import InfluxDBClient
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime
import os
import re
import warnings
import traceback
from influxdb_client.client.warnings import MissingPivotFunction
import pandas as pd

# Suppress warnings
warnings.simplefilter("ignore", MissingPivotFunction)

# ============================================================================
# TEST CONFIGURATION (hardcoded from original export)
# ============================================================================

TEST_NAME = "{test_name}"
START_TIME = datetime.fromisoformat("{start_str}")
STOP_TIME = datetime.fromisoformat("{stop_str}")

# Downsampling
MAX_EXPORT_RATE_HZ = {max_export_rate_hz}
DOWNSAMPLE_WINDOW = "{downsample_window}"

# InfluxDB Connection
INFLUX_URL = "{influx_params['url']}"
INFLUX_ORG = "{influx_params['org']}"
INFLUX_BUCKET = "{influx_params['bucket']}"

# Sensor Labels (embedded from sensor_labels.yaml)
SENSOR_LABELS = {sensor_labels_str}


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

def load_sensor_labels():
    """Return embedded sensor labels."""
    return SENSOR_LABELS


def export_sensor_group(client, output_dir, date_str, 
                        measurement, channels, filename_suffix, 
                        field_name=None, use_channel_tag=False, use_labels=False,
                        downsample=False):
    """Export a group of related sensors to a single CSV."""
    
    ds_info = f" (downsampled to {{MAX_EXPORT_RATE_HZ}} Hz)" if downsample else " (full resolution)"
    print(f"\\nExporting {{filename_suffix}}...{{ds_info}}")
    
    try:
        # Convert time range to UTC for InfluxDB
        start_utc = START_TIME.astimezone(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z')
        stop_utc = STOP_TIME.astimezone(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z')
        
        # Build aggregateWindow line if downsampling
        agg_line = f'  |> aggregateWindow(every: {{DOWNSAMPLE_WINDOW}}, fn: mean, createEmpty: false)\\n' if downsample else ''
        
        if use_channel_tag and field_name:
            channel_filter = ' or '.join([f'r.channel == "{{ch}}"' for ch in channels])
            query = f\'''
from(bucket: "{{INFLUX_BUCKET}}")
  |> range(start: {{start_utc}}, stop: {{stop_utc}})
  |> filter(fn: (r) => r._measurement == "{{measurement}}")
  |> filter(fn: (r) => r._field == "{{field_name}}")
  |> filter(fn: (r) => {{channel_filter}})
{{agg_line}}  |> pivot(rowKey:["_time"], columnKey: ["channel"], valueColumn: "_value")
\'''
        else:
            field_filter = ' or '.join([f'r._field == "{{f}}"' for f in channels])
            query = f\'''
from(bucket: "{{INFLUX_BUCKET}}")
  |> range(start: {{start_utc}}, stop: {{stop_utc}})
  |> filter(fn: (r) => r._measurement == "{{measurement}}")
  |> filter(fn: (r) => {{field_filter}})
{{agg_line}}  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
\'''
        
        df = client.query_api().query_data_frame(query)
        
        if isinstance(df, list):
            df = pd.concat(df, ignore_index=True)
        
        if df.empty:
            print(f"  [!] No data found")
            return None
        
        # Keep only timestamp and data columns
        keep_cols = ['_time'] + [col for col in df.columns if col in channels]
        df = df[keep_cols]
        
        # Sort and dedupe
        df = df.sort_values('_time').drop_duplicates(subset=['_time'])
        
        # Convert timestamps
        df['_time'] = df['_time'].dt.tz_convert('America/Los_Angeles')
        df['_time'] = df['_time'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
        df.rename(columns={{'_time': 'timestamp'}}, inplace=True)
        
        # Rename columns using sensor labels if requested
        if use_labels:
            labels = load_sensor_labels()
            rename_map = {{}}
            for col in df.columns:
                if col == 'timestamp':
                    continue
                if col in labels.get('analog_inputs', {{}}):
                    label_config = labels['analog_inputs'][col]
                    rename_map[col] = label_config.get('label', col) if isinstance(label_config, dict) else label_config
                elif col in labels.get('thermocouples', {{}}):
                    rename_map[col] = labels['thermocouples'][col]
            if rename_map:
                df.rename(columns=rename_map, inplace=True)
        
        # Save CSV
        output_file = f"{{date_str}}_{{filename_suffix}}.csv"
        output_path = output_dir / output_file
        df.to_csv(output_path, index=False, float_format='%.6f')
        
        print(f"  [OK] {{len(df)}} points, {{len(keep_cols)-1}} channels")
        print(f"       File: {{output_file}} ({{os.path.getsize(output_path) / 1024:.1f}} KB)")
        
        return df
        
    except Exception as e:
        print(f"  [ERROR] {{e}}")
        traceback.print_exc()
        return None


def export_bga_data(client, output_dir, date_str):
    """Export BGA data."""
    
    print(f"\\nExporting BGA data... (full resolution)")
    
    labels = load_sensor_labels()
    bga_labels = labels.get('bgas', {{}})
    
    start_utc = START_TIME.astimezone(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z')
    stop_utc = STOP_TIME.astimezone(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z')
    
    try:
        for bga_id in ['BGA01', 'BGA02', 'BGA03']:
            query = f\'''
from(bucket: "{{INFLUX_BUCKET}}")
  |> range(start: {{start_utc}}, stop: {{stop_utc}})
  |> filter(fn: (r) => r._measurement == "bga_metrics")
  |> filter(fn: (r) => r.bga_id == "{{bga_id}}")
  |> filter(fn: (r) => r._field == "purity" or 
                       r._field == "uncertainty" or
                       r._field == "temperature" or
                       r._field == "pressure")
  |> keep(columns: ["_time", "_field", "_value", "primary_gas", "secondary_gas"])
\'''
            
            df = client.query_api().query_data_frame(query)
            
            if isinstance(df, list):
                df = pd.concat(df, ignore_index=True)
            
            if df.empty:
                print(f"  [!] {{bga_id}}: No data found")
                continue
            
            df_pivot = df.pivot_table(
                index='_time', columns='_field', values='_value', aggfunc='first'
            ).reset_index()
            
            if 'primary_gas' in df.columns and 'secondary_gas' in df.columns:
                gas_info = df.groupby('_time')[['primary_gas', 'secondary_gas']].first().reset_index()
                df_pivot = df_pivot.merge(gas_info, on='_time', how='left')
            
            df_pivot = df_pivot.sort_values('_time').drop_duplicates(subset=['_time'])
            df_pivot['_time'] = df_pivot['_time'].dt.tz_convert('America/Los_Angeles')
            df_pivot['_time'] = df_pivot['_time'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
            df_pivot.rename(columns={{'_time': 'timestamp'}}, inplace=True)
            
            bga_label_config = bga_labels.get(bga_id, {{}})
            bga_label = bga_label_config.get('label', bga_id) if isinstance(bga_label_config, dict) else bga_id
            output_file = f"{{date_str}}_BGA_{{bga_label.replace(' ', '_')}}.csv"
            output_path = output_dir / output_file
            df_pivot.to_csv(output_path, index=False, float_format='%.6f')
            
            print(f"  [OK] {{bga_id}}: {{len(df_pivot)}} points")
            print(f"       File: {{output_file}} ({{os.path.getsize(output_path) / 1024:.1f}} KB)")
            
    except Exception as e:
        print(f"  [ERROR] {{e}}")
        traceback.print_exc()


def update_test_info_timestamp():
    """Update CSV export timestamp in test_info.md"""
    info_path = Path(__file__).parent / 'test_info.md'
    if not info_path.exists():
        return
    
    content = info_path.read_text()
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    content = re.sub(
        r'\\| \\*\\*CSV Export\\*\\* \\| .* \\|',
        f'| **CSV Export** | {{time_str}} |',
        content
    )
    info_path.write_text(content)
    print(f"\\nUpdated test_info.md: CSV Export = {{time_str}}")


def main():
    """Export all sensor data."""
    
    date_str = START_TIME.strftime('%Y-%m-%d')
    output_dir = Path(__file__).parent / 'csv'
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print(f"Standalone CSV Export")
    print("=" * 60)
    print(f"Test: {{TEST_NAME}}")
    print(f"Time: {{START_TIME.strftime('%Y-%m-%d %H:%M:%S')}} to {{STOP_TIME.strftime('%H:%M:%S')}}")
    print(f"Output: ./csv/")
    
    # Get token from environment
    token = os.getenv('INFLUXDB_ADMIN_TOKEN')
    if not token:
        print("\\nError: INFLUXDB_ADMIN_TOKEN environment variable not set")
        print("Set it with:")
        print("  export INFLUXDB_ADMIN_TOKEN='your_token_here'")
        return 1
    
    client = InfluxDBClient(url=INFLUX_URL, token=token, org=INFLUX_ORG)
    
    try:
        # Export analog inputs
        ai_channels = [f"AI{{i:02d}}" for i in range(1, 17)]
        export_sensor_group(client, output_dir, date_str,
                          "ni_analog", ai_channels, "AIX",
                          field_name="raw_ma", use_channel_tag=True, downsample=True)
        
        export_sensor_group(client, output_dir, date_str,
                          "ni_analog", ai_channels, "AIX_converted",
                          field_name="value", use_channel_tag=True, use_labels=True, downsample=True)
        
        # Export thermocouples
        tc_channels = [f"TC{{i:02d}}" for i in range(1, 9)]
        export_sensor_group(client, output_dir, date_str,
                          "tc08", tc_channels, "TC",
                          field_name="temp_c", use_channel_tag=True, use_labels=True)
        
        # Export relays
        rl_fields = [f"RL{{i:02d}}" for i in range(1, 17)]
        export_sensor_group(client, output_dir, date_str,
                          "ni_relays", rl_fields, "RL",
                          use_channel_tag=False)
        
        # Export PSU
        psu_fields = ["voltage", "current", "power", "capacity", "runtime", 
                      "battery_v", "temperature", "status", "sys_fault", "mod_fault",
                      "set_voltage_rb", "set_current_rb", "output_enable"]
        export_sensor_group(client, output_dir, date_str,
                          "psu", psu_fields, "PSU",
                          use_channel_tag=False)
        
        # Export BGAs
        export_bga_data(client, output_dir, date_str)
        
        print("\\n" + "=" * 60)
        print("[OK] Export complete")
        print("=" * 60)
        
        # Update timestamp
        update_test_info_timestamp()
        
    finally:
        client.close()
    
    return 0


if __name__ == "__main__":
    exit(main())
'''
    
    return script


def save_standalone_export_csv(output_dir: Path, script_content: str) -> None:
    """Save standalone export_csv.py to the export folder."""
    script_path = output_dir / 'export_csv.py'
    with open(script_path, 'w') as f:
        f.write(script_content)


def generate_standalone_plot_data(
    test_name: str,
    start_time: datetime,
    stop_time: datetime,
    plot_dpi: int = 300,
    plot_format: str = 'jpg',
    figure_size: tuple = (12, 6),
    max_plot_points: int = 50000
) -> str:
    """Generate a standalone plot_data.py script with hardcoded parameters.
    
    Returns:
        Python script as a string
    """
    
    # Load current config to embed
    sensor_labels = load_sensor_labels()
    
    # Build sensor labels dict as Python literal
    def dict_to_python(d, indent=0):
        """Convert dict to Python literal string."""
        lines = ["{"]
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{'    ' * (indent+1)}'{k}': {dict_to_python(v, indent+1)},")
            elif isinstance(v, str):
                # Escape single quotes in strings
                v_escaped = v.replace("'", "\\'")
                lines.append(f"{'    ' * (indent+1)}'{k}': '{v_escaped}',")
            else:
                lines.append(f"{'    ' * (indent+1)}'{k}': {v},")
        lines.append(f"{'    ' * indent}}}")
        return '\n'.join(lines)
    
    sensor_labels_str = dict_to_python(sensor_labels, indent=0)
    date_str = start_time.strftime('%Y-%m-%d')
    
    script = f'''#!/usr/bin/env python3
"""
Standalone Plot Generation Script - {test_name}

This script regenerates the plots from the CSV files.
Run from the export folder: python plot_data.py

Requirements:
  - pandas
  - matplotlib

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime
import re
import os

# ============================================================================
# CONFIGURATION (hardcoded from original export)
# ============================================================================

TEST_NAME = "{test_name}"
DATE_STR = "{date_str}"

# Plot settings
PLOT_DPI = {plot_dpi}
PLOT_FORMAT = '{plot_format}'
FIGURE_SIZE = {figure_size}
MAX_PLOT_POINTS = {max_plot_points}

# Sensor Labels (embedded from sensor_labels.yaml)
SENSOR_LABELS = {sensor_labels_str}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def decimate_for_plot(df, max_points=MAX_PLOT_POINTS):
    """Decimate dataframe for plotting."""
    if len(df) <= max_points:
        return df
    step = len(df) // max_points
    return df.iloc[::step].copy()


def get_shading_periods():
    """Get purge and active periods for plot shading."""
    csv_dir = Path(__file__).parent / 'csv'
    
    bga_labels = SENSOR_LABELS.get('bgas', {{}})
    bga01_config = bga_labels.get('BGA01', {{}})
    bga01_label = bga01_config.get('label', 'BGA01') if isinstance(bga01_config, dict) else 'BGA01'
    bga_path = csv_dir / f"{{DATE_STR}}_BGA_{{bga01_label.replace(' ', '_')}}.csv"
    psu_path = csv_dir / f"{{DATE_STR}}_PSU.csv"
    
    purge_periods = []
    active_periods = []
    
    if bga_path.exists():
        df_bga = pd.read_csv(bga_path, parse_dates=['timestamp'])
        if 'secondary_gas' in df_bga.columns:
            df_bga['is_purge'] = df_bga['secondary_gas'] == '7727-37-9'
            purge_changes = df_bga['is_purge'].ne(df_bga['is_purge'].shift())
            purge_groups = purge_changes.cumsum()
            for group_id, group_df in df_bga[df_bga['is_purge']].groupby(purge_groups):
                if not group_df.empty:
                    purge_periods.append((group_df['timestamp'].min(), group_df['timestamp'].max()))
    
    if psu_path.exists():
        df_psu = pd.read_csv(psu_path, parse_dates=['timestamp'])
        if 'current' in df_psu.columns:
            df_psu['is_active'] = df_psu['current'] > 1.0
            active_changes = df_psu['is_active'].ne(df_psu['is_active'].shift())
            active_groups = active_changes.cumsum()
            for group_id, group_df in df_psu[df_psu['is_active']].groupby(active_groups):
                if not group_df.empty:
                    active_periods.append((group_df['timestamp'].min(), group_df['timestamp'].max()))
    
    return purge_periods, active_periods


def add_shading(ax, purge_periods, active_periods):
    """Add purge and active period shading to a plot."""
    for start, end in purge_periods:
        ax.axvspan(start, end, alpha=0.15, color='gray', zorder=0)
    for start, end in active_periods:
        ax.axvspan(start, end, alpha=0.1, color='cyan', zorder=0)


# ============================================================================
# PLOT FUNCTIONS
# ============================================================================

def plot_analog_inputs(csv_dir, plots_dir, purge_periods, active_periods):
    """Plot analog input channels."""
    csv_path = csv_dir / f"{{DATE_STR}}_AIX.csv"
    if not csv_path.exists():
        print("  [!] AIX.csv not found")
        return
    
    df = pd.read_csv(csv_path, parse_dates=['timestamp'])
    df_plot = decimate_for_plot(df)
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    add_shading(ax, purge_periods, active_periods)
    
    plotted = 0
    for i in range(1, 17):
        col = f'AI{{i:02d}}'
        if col in df.columns and df[col].max() > 1.0:
            ax.plot(df_plot['timestamp'], df_plot[col], label=col, linewidth=0.8)
            plotted += 1
    
    if plotted == 0:
        plt.close()
        return
    
    ax.set_xlabel('Time')
    ax.set_ylabel('Current [mA]')
    ax.set_title('Analog Inputs (Raw)')
    ax.set_ylim(0, 25)
    ax.set_xlim(df['timestamp'].min(), df['timestamp'].max())
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=4, fontsize=8, frameon=False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.savefig(plots_dir / f"analog_inputs.{{PLOT_FORMAT}}", dpi=PLOT_DPI)
    plt.close()
    print(f"  [OK] analog_inputs.{{PLOT_FORMAT}}")


def plot_temperatures(csv_dir, plots_dir, purge_periods, active_periods):
    """Plot temperatures."""
    tc_path = csv_dir / f"{{DATE_STR}}_TC.csv"
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    add_shading(ax, purge_periods, active_periods)
    
    plotted = 0
    time_range = None
    
    if tc_path.exists():
        df_tc = pd.read_csv(tc_path, parse_dates=['timestamp'])
        time_range = (df_tc['timestamp'].min(), df_tc['timestamp'].max())
        df_tc_plot = decimate_for_plot(df_tc)
        for col in df_tc.columns:
            if col != 'timestamp':
                valid = (df_tc[col] > -200) & (df_tc[col] < 1500)
                if valid.any():
                    ax.plot(df_tc_plot['timestamp'], df_tc_plot[col], label=col, linewidth=0.8, alpha=0.7)
                    plotted += 1
    
    # Plot BGA temperatures
    bga_labels = SENSOR_LABELS.get('bgas', {{}})
    colors = ['red', 'orange', 'purple']
    for idx, bga_id in enumerate(['BGA01', 'BGA02', 'BGA03']):
        bga_config = bga_labels.get(bga_id, {{}})
        bga_label = bga_config.get('label', bga_id) if isinstance(bga_config, dict) else bga_id
        bga_path = csv_dir / f"{{DATE_STR}}_BGA_{{bga_label.replace(' ', '_')}}.csv"
        if bga_path.exists():
            df_bga = pd.read_csv(bga_path, parse_dates=['timestamp'])
            if time_range is None:
                time_range = (df_bga['timestamp'].min(), df_bga['timestamp'].max())
            df_bga_plot = decimate_for_plot(df_bga)
            if 'temperature' in df_bga.columns:
                ax.plot(df_bga_plot['timestamp'], df_bga_plot['temperature'],
                        label=f'{{bga_label}} Temp', linewidth=1.5, color=colors[idx], linestyle='--')
                plotted += 1
    
    if plotted == 0:
        plt.close()
        return
    
    ax.set_xlabel('Time')
    ax.set_ylabel('Temperature [°C]')
    ax.set_title('Temperatures')
    ax.set_ylim(0, 130)
    if time_range:
        ax.set_xlim(time_range[0], time_range[1])
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=3, fontsize=8, frameon=False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.savefig(plots_dir / f"temperatures.{{PLOT_FORMAT}}", dpi=PLOT_DPI)
    plt.close()
    print(f"  [OK] temperatures.{{PLOT_FORMAT}}")


def plot_gas_purity(csv_dir, plots_dir, purge_periods, active_periods, ylim=(0, 100), suffix=""):
    """Plot BGA purity."""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    add_shading(ax, purge_periods, active_periods)
    
    time_range = None
    plotted = 0
    colors = ['blue', 'green', 'purple']
    bga_labels = SENSOR_LABELS.get('bgas', {{}})
    
    for idx, bga_id in enumerate(['BGA01', 'BGA02', 'BGA03']):
        bga_config = bga_labels.get(bga_id, {{}})
        bga_label = bga_config.get('label', bga_id) if isinstance(bga_config, dict) else bga_id
        bga_path = csv_dir / f"{{DATE_STR}}_BGA_{{bga_label.replace(' ', '_')}}.csv"
        if bga_path.exists():
            df = pd.read_csv(bga_path, parse_dates=['timestamp'])
            if time_range is None:
                time_range = (df['timestamp'].min(), df['timestamp'].max())
            df_plot = decimate_for_plot(df)
            if 'purity' in df.columns:
                ax.plot(df_plot['timestamp'], df_plot['purity'],
                        label=bga_label, linewidth=1.5, marker='.', markersize=2, color=colors[idx])
                plotted += 1
    
    if plotted == 0:
        plt.close()
        return
    
    ax.set_xlabel('Time')
    ax.set_ylabel('Purity [%]')
    ax.set_title('Gas Purity (Detail)' if ylim == (90, 100) else 'Gas Purity')
    ax.set_ylim(ylim[0], ylim[1])
    if time_range:
        ax.set_xlim(time_range[0], time_range[1])
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=3, fontsize=8, frameon=False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.savefig(plots_dir / f"gas_purity{{suffix}}.{{PLOT_FORMAT}}", dpi=PLOT_DPI)
    plt.close()
    print(f"  [OK] gas_purity{{suffix}}.{{PLOT_FORMAT}}")


def plot_power(csv_dir, plots_dir, purge_periods, active_periods):
    """Plot PSU power."""
    csv_path = csv_dir / f"{{DATE_STR}}_PSU.csv"
    if not csv_path.exists():
        print("  [!] PSU.csv not found")
        return
    
    df = pd.read_csv(csv_path, parse_dates=['timestamp'])
    if 'power' not in df.columns:
        return
    
    df_plot = decimate_for_plot(df)
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    add_shading(ax, purge_periods, active_periods)
    
    ax.plot(df_plot['timestamp'], df_plot['power'] / 1000, linewidth=1.5, color='green')
    
    ax.set_xlabel('Time')
    ax.set_ylabel('Power [kW]')
    ax.set_title('PSU Power')
    ax.set_ylim(0, 45)
    ax.set_xlim(df['timestamp'].min(), df['timestamp'].max())
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.savefig(plots_dir / f"power.{{PLOT_FORMAT}}", dpi=PLOT_DPI)
    plt.close()
    print(f"  [OK] power.{{PLOT_FORMAT}}")


def update_test_info_timestamp():
    """Update Plot export timestamp in test_info.md"""
    info_path = Path(__file__).parent / 'test_info.md'
    if not info_path.exists():
        return
    
    content = info_path.read_text()
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    content = re.sub(
        r'\\| \\*\\*Plot Export\\*\\* \\| .* \\|',
        f'| **Plot Export** | {{time_str}} |',
        content
    )
    info_path.write_text(content)
    print(f"\\nUpdated test_info.md: Plot Export = {{time_str}}")


def main():
    """Generate all plots."""
    
    csv_dir = Path(__file__).parent / 'csv'
    plots_dir = Path(__file__).parent / 'plots'
    plots_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print(f"Standalone Plot Generation")
    print("=" * 60)
    print(f"Test: {{TEST_NAME}}")
    print(f"Input: ./csv/")
    print(f"Output: ./plots/")
    print()
    
    purge_periods, active_periods = get_shading_periods()
    
    plot_analog_inputs(csv_dir, plots_dir, purge_periods, active_periods)
    plot_temperatures(csv_dir, plots_dir, purge_periods, active_periods)
    plot_gas_purity(csv_dir, plots_dir, purge_periods, active_periods, ylim=(0, 100))
    plot_gas_purity(csv_dir, plots_dir, purge_periods, active_periods, ylim=(90, 100), suffix="_detail")
    plot_power(csv_dir, plots_dir, purge_periods, active_periods)
    
    print()
    print("=" * 60)
    print("[OK] Plots complete")
    print("=" * 60)
    
    update_test_info_timestamp()
    
    return 0


if __name__ == "__main__":
    exit(main())
'''
    
    return script


def save_standalone_plot_data(output_dir: Path, script_content: str) -> None:
    """Save standalone plot_data.py to the export folder."""
    script_path = output_dir / 'plot_data.py'
    with open(script_path, 'w') as f:
        f.write(script_content)

