"""
Gen3 AWE Test Data Processing Configuration

EDIT THIS FILE to configure test parameters.
Sensor configurations are in MK1_AWE/config/devices.yaml (single source of truth).
Then run: python process_test.py

Gen3 Measurements (sample rates configured in devices.yaml):
  - ni_analog: 16 analog inputs (AI01-AI16)
  - tc08: 8 thermocouples (TC01-TC08)
  - ni_relays: 16 relay states (RL01-RL16)
  - psu: PSU data (voltage, current, power, etc.)
  - bga_metrics: 3 BGAs (purity, uncertainty, temp, pressure)
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import sys
import os

# Add path to import config_loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'gui'))
from config_loader import get_sensor_conversions

# Test Info
TEST_NAME = "Gen3_Test_1"

# Time Range (Pacific Time - PT)
# EDIT THESE for your test:
START_TIME = datetime(2025, 11, 17, 12, 41, 30, tzinfo=ZoneInfo('America/Los_Angeles'))
STOP_TIME = datetime(2025, 11, 17, 12, 45, 0, tzinfo=ZoneInfo('America/Los_Angeles'))

# Auto-convert to UTC for InfluxDB queries
START_TIME_UTC = START_TIME.astimezone(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z')
STOP_TIME_UTC = STOP_TIME.astimezone(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z')

# Sensor Conversions (loaded from devices.yaml)
SENSOR_CONVERSIONS = get_sensor_conversions()

# Export Downsampling Settings
# Sensors faster than MAX_EXPORT_RATE_HZ get downsampled (e.g., NI analog 1000Hz → 10Hz)
MAX_EXPORT_RATE_HZ = 10
DOWNSAMPLE_WINDOW = f"{int(1000 / MAX_EXPORT_RATE_HZ)}ms"  # "100ms" for 10 Hz

# Plot Settings
PLOT_DPI = 300
PLOT_FORMAT = 'jpg'
FIGURE_SIZE = (12, 6)
MAX_PLOT_POINTS = 50000  # Higher threshold now that data is downsampled (10 Hz max)

