#!/usr/bin/env python3
"""
Generate test_info.md - Human-readable test documentation

Creates a Markdown document with:
- Test metadata (name, time range, timezone)
- Sensor configuration (from sensor_labels.yaml)
- Hardware summary (from devices.yaml)
- Export timestamps (CSV and plot dates)
"""

from datetime import datetime
from pathlib import Path
import sys
import os

# Add path to import config_loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'gui'))
from config_loader import load_sensor_labels, load_devices_config


def generate_test_info_md(
    test_name: str,
    start_time: datetime,
    stop_time: datetime,
    csv_export_time: datetime = None,
    plot_export_time: datetime = None,
    max_export_rate_hz: int = 10
) -> str:
    """Generate test_info.md content as a string.
    
    Args:
        test_name: Name of the test
        start_time: Test start time (with timezone)
        stop_time: Test stop time (with timezone)
        csv_export_time: When CSVs were exported (None if not yet)
        plot_export_time: When plots were generated (None if not yet)
        max_export_rate_hz: Max sample rate for exports (downsampling target)
    
    Returns:
        Markdown string for test_info.md
    """
    
    # Load configurations
    sensor_labels = load_sensor_labels()
    devices_config = load_devices_config()
    
    # Format times
    tz_name = str(start_time.tzinfo)
    duration = stop_time - start_time
    duration_str = str(duration).split('.')[0]  # Remove microseconds
    
    csv_time_str = csv_export_time.strftime('%Y-%m-%d %H:%M:%S') if csv_export_time else "Not exported"
    plot_time_str = plot_export_time.strftime('%Y-%m-%d %H:%M:%S') if plot_export_time else "Not exported"
    
    # Build the Markdown content
    lines = []
    
    # Header
    lines.append(f"# Test: {test_name}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Test Metadata
    lines.append("## Test Metadata")
    lines.append("")
    lines.append(f"| Property | Value |")
    lines.append(f"|----------|-------|")
    lines.append(f"| **Test Name** | {test_name} |")
    lines.append(f"| **Start Time** | {start_time.strftime('%Y-%m-%d %H:%M:%S')} |")
    lines.append(f"| **Stop Time** | {stop_time.strftime('%H:%M:%S')} |")
    lines.append(f"| **Duration** | {duration_str} |")
    lines.append(f"| **Timezone** | {tz_name} |")
    lines.append("")
    
    # Export Timestamps
    lines.append("## Export Timestamps")
    lines.append("")
    lines.append(f"| Export Type | Timestamp |")
    lines.append(f"|-------------|-----------|")
    lines.append(f"| **CSV Export** | {csv_time_str} |")
    lines.append(f"| **Plot Export** | {plot_time_str} |")
    lines.append("")
    
    # Sample Rates
    lines.append("## Sample Rates")
    lines.append("")
    bridges = devices_config.get('bridges', {})
    lines.append(f"| Measurement | Native Rate | Export Rate |")
    lines.append(f"|-------------|-------------|-------------|")
    
    for bridge_name, bridge_config in bridges.items():
        native_rate = bridge_config.get('sample_rate', '?')
        if native_rate > max_export_rate_hz:
            export_rate = f"{max_export_rate_hz} Hz (downsampled)"
        else:
            export_rate = f"{native_rate} Hz"
        lines.append(f"| {bridge_name} | {native_rate} Hz | {export_rate} |")
    lines.append("")
    
    # Analog Inputs
    lines.append("## Analog Inputs (16 channels)")
    lines.append("")
    lines.append(f"| Channel | Label | Type | Range | Unit |")
    lines.append(f"|---------|-------|------|-------|------|")
    
    analog_inputs = sensor_labels.get('analog_inputs', {})
    for ch in [f"AI{i:02d}" for i in range(1, 17)]:
        config = analog_inputs.get(ch, {})
        if isinstance(config, dict):
            label = config.get('label', ch)
            sensor_type = config.get('sensor_type', '-')
            eng_min = config.get('eng_min', 0)
            eng_max = config.get('eng_max', 100)
            eng_unit = config.get('eng_unit', '-')
            range_str = f"{eng_min} - {eng_max}"
        else:
            label = config if config else ch
            sensor_type = '-'
            range_str = '-'
            eng_unit = '-'
        lines.append(f"| {ch} | {label} | {sensor_type} | {range_str} | {eng_unit} |")
    lines.append("")
    
    # Thermocouples
    lines.append("## Thermocouples (8 channels)")
    lines.append("")
    lines.append(f"| Channel | Label | Type |")
    lines.append(f"|---------|-------|------|")
    
    thermocouples = sensor_labels.get('thermocouples', {})
    for ch in [f"TC{i:02d}" for i in range(1, 9)]:
        label = thermocouples.get(ch, ch)
        lines.append(f"| {ch} | {label} | K-type |")
    lines.append("")
    
    # BGAs
    lines.append("## Binary Gas Analyzers (3 units)")
    lines.append("")
    
    # Gas CAS number reference
    gas_ref = devices_config.get('gas_reference', {})
    gas_names = {v: k for k, v in gas_ref.items()}  # Invert for lookup
    
    lines.append(f"| ID | Label | Primary Gas | Secondary Gas | Purge Gas |")
    lines.append(f"|----|-------|-------------|---------------|-----------|")
    
    bgas = sensor_labels.get('bgas', {})
    for bga_id in ['BGA01', 'BGA02', 'BGA03']:
        config = bgas.get(bga_id, {})
        if isinstance(config, dict):
            label = config.get('label', bga_id)
            gases = config.get('gases', {})
            primary = gas_ref.get(gases.get('primary', ''), gases.get('primary', '-'))
            secondary = gas_ref.get(gases.get('secondary', ''), gases.get('secondary', '-'))
            purge = gas_ref.get(gases.get('purge', ''), gases.get('purge', '-'))
        else:
            label = config if config else bga_id
            primary = secondary = purge = '-'
        lines.append(f"| {bga_id} | {label} | {primary} | {secondary} | {purge} |")
    lines.append("")
    
    # Relays
    lines.append("## Relays (16 channels)")
    lines.append("")
    lines.append(f"| Channel | Label |")
    lines.append(f"|---------|-------|")
    
    relays = sensor_labels.get('relays', {})
    for ch in [f"RL{i:02d}" for i in range(1, 17)]:
        label = relays.get(ch, ch)
        lines.append(f"| {ch} | {label} |")
    lines.append("")
    
    # Hardware Info
    lines.append("## Hardware Configuration")
    lines.append("")
    
    devices = devices_config.get('devices', {})
    
    # NI cDAQ
    ni_cdaq = devices.get('NI_cDAQ', {})
    if ni_cdaq:
        lines.append(f"### NI cDAQ")
        lines.append(f"- **Name:** {ni_cdaq.get('name', 'N/A')}")
        lines.append(f"- **IP:** {ni_cdaq.get('ip', 'N/A')}")
        lines.append(f"- **Slots:** {', '.join(f'{k}: {v}' for k, v in ni_cdaq.get('slots', {}).items())}")
        lines.append("")
    
    # PSU
    psu = devices.get('PSU', {})
    if psu:
        lines.append(f"### Power Supply")
        lines.append(f"- **Protocol:** {psu.get('protocol', 'N/A')}")
        lines.append(f"- **COM Port:** {psu.get('com_port', 'N/A')}")
        lines.append(f"- **Baud Rate:** {psu.get('baud_rate', 'N/A')}")
        lines.append("")
    
    # Pico TC-08
    pico = devices.get('Pico_TC08', {})
    if pico:
        lines.append(f"### Pico TC-08")
        lines.append(f"- **Protocol:** {pico.get('protocol', 'N/A')}")
        lines.append(f"- **Channels:** {pico.get('channels', 'N/A')}")
        lines.append("")
    
    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by Gen3 AWE Test Rig data export system*")
    lines.append("")
    
    return '\n'.join(lines)


def save_test_info_md(output_path: Path, content: str) -> None:
    """Save test_info.md to disk."""
    with open(output_path, 'w') as f:
        f.write(content)


def update_export_timestamp(md_path: Path, export_type: str, timestamp: datetime) -> None:
    """Update a specific export timestamp in an existing test_info.md file.
    
    Args:
        md_path: Path to test_info.md
        export_type: 'csv' or 'plot'
        timestamp: New timestamp to set
    """
    if not md_path.exists():
        return
    
    content = md_path.read_text()
    time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
    
    if export_type == 'csv':
        # Replace CSV export line
        import re
        content = re.sub(
            r'\| \*\*CSV Export\*\* \| .* \|',
            f'| **CSV Export** | {time_str} |',
            content
        )
    elif export_type == 'plot':
        # Replace Plot export line
        import re
        content = re.sub(
            r'\| \*\*Plot Export\*\* \| .* \|',
            f'| **Plot Export** | {time_str} |',
            content
        )
    
    md_path.write_text(content)


if __name__ == "__main__":
    # Test the template generation
    from zoneinfo import ZoneInfo
    
    test_start = datetime(2025, 12, 19, 10, 0, 0, tzinfo=ZoneInfo('America/Los_Angeles'))
    test_stop = datetime(2025, 12, 19, 11, 0, 0, tzinfo=ZoneInfo('America/Los_Angeles'))
    
    content = generate_test_info_md(
        test_name="Example_Test",
        start_time=test_start,
        stop_time=test_stop,
        csv_export_time=datetime.now(),
        plot_export_time=None
    )
    
    print(content)

