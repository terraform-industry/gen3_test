#!/usr/bin/env python3
"""
Gen3 AWE Complete Test Data Processing Pipeline

Edit test_config.py to configure, then run: python process_test.py
"""

import subprocess
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

# All configuration now in test_config.py - edit that file!
from test_config import (
    TEST_NAME, START_TIME, STOP_TIME, START_TIME_UTC, STOP_TIME_UTC,
    DOWNSAMPLE_AIX, DOWNSAMPLE_TC, DOWNSAMPLE_PSU, DOWNSAMPLE_BGA, DOWNSAMPLE_RL,
    DOWNSAMPLE_FUNCTION, PLOT_DPI, PLOT_FORMAT, FIGURE_SIZE
)


def run_export():
    """Run CSV export (uses test_config.py)"""
    print("=" * 70)
    print("STEP 1: Exporting CSV data from InfluxDB")
    print("=" * 70)
    print()
    
    export_script = Path(__file__).parent / 'export_csv.py'
    result = subprocess.run([sys.executable, str(export_script)])
    
    if result.returncode != 0:
        print("\n[ERROR] CSV export failed")
        sys.exit(1)
    
    print()


def run_plotting():
    """Generate plots (uses test_config.py)"""
    print("=" * 70)
    print("STEP 2: Generating plots from CSV data")
    print("=" * 70)
    print()
    
    plot_script = Path(__file__).parent / 'plot_data.py'
    result = subprocess.run([sys.executable, str(plot_script)])
    
    if result.returncode != 0:
        print("\n[ERROR] Plotting failed")
        sys.exit(1)
    
    print()


def save_test_config(output_dir):
    """Save complete test configuration to output directory"""
    config_log = {
        'test_info': {
            'test_name': TEST_NAME,
            'start_time_local': START_TIME.isoformat(),
            'stop_time_local': STOP_TIME.isoformat(),
            'start_time_utc': START_TIME_UTC,
            'stop_time_utc': STOP_TIME_UTC,
            'timezone': str(START_TIME.tzinfo),
            'processed_at': datetime.now().isoformat()
        },
        'downsampling': {
            'AIX': DOWNSAMPLE_AIX,
            'TC': DOWNSAMPLE_TC,
            'PSU': DOWNSAMPLE_PSU,
            'BGA': DOWNSAMPLE_BGA,
            'RL': DOWNSAMPLE_RL,
            'function': DOWNSAMPLE_FUNCTION
        },
        'plot_settings': {
            'dpi': PLOT_DPI,
            'format': PLOT_FORMAT,
            'figure_size': FIGURE_SIZE
        }
    }
    
    # Save as JSON
    config_path = output_dir / 'test_config.json'
    with open(config_path, 'w') as f:
        json.dump(config_log, f, indent=2)
    
    # Also save a copy of devices.yaml
    devices_yaml_src = Path(__file__).parent.parent / 'config' / 'devices.yaml'
    devices_yaml_dst = output_dir / 'devices.yaml'
    shutil.copy2(devices_yaml_src, devices_yaml_dst)
    
    print(f"  Config saved: test_config.json")
    print(f"  Devices snapshot: devices.yaml")


def main():
    """Main processing pipeline"""
    print()
    print("=" * 70)
    print("GEN3 AWE TEST DATA PROCESSING")
    print("=" * 70)
    print(f"Test: {TEST_NAME}")
    print(f"Time: {START_TIME.strftime('%Y-%m-%d %H:%M')} to {STOP_TIME.strftime('%H:%M %Z')}")
    print()
    
    # Create output directory
    date_str = START_TIME.strftime('%Y-%m-%d')
    output_dir = Path(__file__).parent / f"{date_str}_{TEST_NAME}"
    output_dir.mkdir(exist_ok=True)
    
    # Save configuration snapshot
    print("Saving configuration...")
    save_test_config(output_dir)
    print()
    
    # Step 1: Export CSVs
    run_export()
    
    # Step 2: Generate plots
    run_plotting()
    
    print("=" * 70)
    print("[OK] PROCESSING COMPLETE")
    print("=" * 70)
    print()
    print(f"Output directory: {output_dir.name}/")
    print("  - CSVs: YYYY-MM-DD_*.csv")
    print("  - Plots: plots/*.jpg")
    print("  - Config: test_config.json, devices.yaml")
    print()


if __name__ == "__main__":
    main()

