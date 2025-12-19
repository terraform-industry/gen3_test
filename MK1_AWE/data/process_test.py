#!/usr/bin/env python3
"""
Gen3 AWE Complete Test Data Processing Pipeline

Edit test_config.py to configure, then run: python process_test.py
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

# All configuration now in test_config.py - edit that file!
from test_config import (
    TEST_NAME, START_TIME, STOP_TIME,
    MAX_EXPORT_RATE_HZ
)

# Import test info generator
from generate_test_info import generate_test_info_md, save_test_info_md, update_export_timestamp

# Import standalone script generators
from generate_standalone_scripts import (
    generate_standalone_export_csv, save_standalone_export_csv,
    generate_standalone_plot_data, save_standalone_plot_data
)

from test_config import PLOT_DPI, PLOT_FORMAT, FIGURE_SIZE, MAX_PLOT_POINTS


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


def save_test_info(output_dir, csv_export_time=None, plot_export_time=None):
    """Generate test_info.md with sensor labels and device config"""
    
    content = generate_test_info_md(
        test_name=TEST_NAME,
        start_time=START_TIME,
        stop_time=STOP_TIME,
        csv_export_time=csv_export_time,
        plot_export_time=plot_export_time,
        max_export_rate_hz=MAX_EXPORT_RATE_HZ
    )
    
    info_path = output_dir / 'test_info.md'
    save_test_info_md(info_path, content)
    
    print(f"  Test info saved: test_info.md")


def save_standalone_scripts(output_dir):
    """Generate and save standalone export/plot scripts to the output folder"""
    
    # Generate standalone export_csv.py
    export_script = generate_standalone_export_csv(
        test_name=TEST_NAME,
        start_time=START_TIME,
        stop_time=STOP_TIME,
        max_export_rate_hz=MAX_EXPORT_RATE_HZ
    )
    save_standalone_export_csv(output_dir, export_script)
    print(f"  Standalone script: export_csv.py")
    
    # Generate standalone plot_data.py
    plot_script = generate_standalone_plot_data(
        test_name=TEST_NAME,
        start_time=START_TIME,
        stop_time=STOP_TIME,
        plot_dpi=PLOT_DPI,
        plot_format=PLOT_FORMAT,
        figure_size=FIGURE_SIZE,
        max_plot_points=MAX_PLOT_POINTS
    )
    save_standalone_plot_data(output_dir, plot_script)
    print(f"  Standalone script: plot_data.py")


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
    
    # Step 1: Export CSVs
    run_export()
    csv_export_time = datetime.now()
    
    # Step 2: Generate plots
    run_plotting()
    plot_export_time = datetime.now()
    
    # Save test info and standalone scripts
    print("Saving test documentation and scripts...")
    save_test_info(output_dir, csv_export_time, plot_export_time)
    save_standalone_scripts(output_dir)
    print()
    
    print("=" * 70)
    print("[OK] PROCESSING COMPLETE")
    print("=" * 70)
    print()
    print(f"Output directory: {output_dir.name}/")
    print("  - csv/: CSV data files")
    print("  - plots/: Plot images")
    print("  - test_info.md: Test documentation")
    print("  - export_csv.py: Standalone CSV regeneration script")
    print("  - plot_data.py: Standalone plot regeneration script")
    print()


if __name__ == "__main__":
    main()

