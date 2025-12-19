"""
Gen3 AWE Test Data Processing Configuration

EDIT THIS FILE to configure test parameters.
Sensor configurations are in MK1_AWE/config/devices.yaml (single source of truth).
Then run: python process_test.py

Gen3 Measurements:
  - ni_analog: 16 analog inputs (AI01-AI16) at 10Hz
  - tc08: 8 thermocouples (TC01-TC08) at 1Hz
  - ni_relays: 16 relay states (RL01-RL16) at 10Hz
  - psu: PSU data (voltage, current, power, etc.) at 10Hz
  - bga_metrics: 3 BGAs (purity, uncertainty, temp, pressure) at 2Hz
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

# Downsampling Windows (adjust based on test duration)
DOWNSAMPLE_AIX = "100ms"     # Analog inputs (10Hz native)
DOWNSAMPLE_TC = "1s"         # Thermocouples (1Hz native)
DOWNSAMPLE_PSU = "100ms"     # PSU (10Hz native)
DOWNSAMPLE_BGA = "500ms"     # BGAs (2Hz native)
DOWNSAMPLE_RL = "100ms"      # Relays (10Hz native)
DOWNSAMPLE_FUNCTION = "mean" # mean, median, max, min, first, last

# Sensor Conversions (loaded from devices.yaml)
SENSOR_CONVERSIONS = get_sensor_conversions()

# Plot Settings
PLOT_DPI = 300
PLOT_FORMAT = 'jpg'
FIGURE_SIZE = (12, 6)

