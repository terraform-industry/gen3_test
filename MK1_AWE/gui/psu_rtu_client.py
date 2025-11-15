#!/usr/bin/env python3
"""
PSU Modbus RTU Control Client
Controls single PSU via RS485/USB adapter
"""

import minimalmodbus
import yaml
import time
import threading
from pathlib import Path
from typing import Optional, Dict

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"

# Safety limits
VOLTAGE_MIN = 100.0  # V
VOLTAGE_MAX = 900.0  # V
CURRENT_MIN = 1.0    # A
CURRENT_MAX = 100.0  # A

# Global lock for thread safety
psu_lock = threading.Lock()


class PSUClient:
    """Client for controlling PSU via Modbus RTU"""
    
    def __init__(self):
        self.config = self._load_config()
        self.psu_config = self.config['devices']['PSU']
        self.com_port = self.psu_config['com_port']
        self.psu = None
        self._setup_connection()
    
    def _load_config(self):
        """Load configuration from devices.yaml"""
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    
    def _setup_connection(self):
        """Setup Modbus connection"""
        if not self.com_port:
            raise ValueError("COM port not configured in devices.yaml")
        
        self.psu = minimalmodbus.Instrument(self.com_port, self.psu_config['slave_id'])
        self.psu.serial.baudrate = self.psu_config['baud_rate']
        self.psu.mode = minimalmodbus.MODE_RTU
        self.psu.serial.timeout = self.psu_config['timeout']
        self.psu.close_port_after_each_call = True  # Essential for USB adapters
    
    def set_voltage_current(self, voltage: float, current: float) -> bool:
        """
        Set voltage and current with safety limits
        
        Args:
            voltage: Target voltage (V)
            current: Target current (A)
        
        Returns:
            True if successful
        
        Safety logic:
            - voltage < 100V or current < 1A → 0V, 0A, output OFF
            - Within bounds → set V/I, output ON
            - Above max → clamp to max
        """
        with psu_lock:
            try:
                # Apply safety limits
                if voltage < VOLTAGE_MIN or current < CURRENT_MIN:
                    # Below minimum → safe state (0V, 0A, OFF)
                    print(f"Below safety limits → Setting safe state (0V, 0A, OFF)")
                    voltage = 0.0
                    current = 0.0
                    enable = False
                else:
                    # Clamp to max limits
                    voltage = min(voltage, VOLTAGE_MAX)
                    current = min(current, CURRENT_MAX)
                    enable = True
                
                # Write voltage (register 0x0101, scale 0.1)
                self.psu.write_register(0x0101, int(voltage / 0.1))
                time.sleep(0.1)  # Essential delay between writes
                
                # Write current (register 0x0102, scale 0.1)
                self.psu.write_register(0x0102, int(current / 0.1))
                time.sleep(0.1)
                
                # Write output enable (register 0x0103)
                self.psu.write_register(0x0103, 1 if enable else 0)
                
                print(f"✓ PSU set: {voltage:.1f}V, {current:.1f}A, {'ON' if enable else 'OFF'}")
                return True
            
            except Exception as e:
                print(f"✗ Failed to set PSU: {e}")
                return False
    
    def set_voltage(self, voltage: float) -> bool:
        """Set voltage only (keeps current unchanged)"""
        current = self.get_current() or 0.0
        return self.set_voltage_current(voltage, current)
    
    def set_current(self, current: float) -> bool:
        """Set current only (keeps voltage unchanged)"""
        voltage = self.get_voltage() or 0.0
        return self.set_voltage_current(voltage, current)
    
    def enable_output(self) -> bool:
        """Enable PSU output"""
        with psu_lock:
            try:
                self.psu.write_register(0x0103, 1)
                print("✓ PSU output enabled")
                return True
            except Exception as e:
                print(f"✗ Failed to enable PSU: {e}")
                return False
    
    def disable_output(self) -> bool:
        """Disable PSU output"""
        with psu_lock:
            try:
                self.psu.write_register(0x0103, 0)
                print("✓ PSU output disabled")
                return True
            except Exception as e:
                print(f"✗ Failed to disable PSU: {e}")
                return False
    
    def safe_shutdown(self) -> bool:
        """Set PSU to safe state: 0V, 0A, output OFF"""
        return self.set_voltage_current(0.0, 0.0)
    
    def get_voltage(self) -> Optional[float]:
        """Read actual output voltage"""
        with psu_lock:
            try:
                raw = self.psu.read_register(0x0001)
                return raw * 0.1
            except Exception as e:
                print(f"✗ Failed to read voltage: {e}")
                return None
    
    def get_current(self) -> Optional[float]:
        """Read actual output current"""
        with psu_lock:
            try:
                raw = self.psu.read_register(0x0002)
                return raw * 0.1
            except Exception as e:
                print(f"✗ Failed to read current: {e}")
                return None
    
    def get_power(self) -> Optional[float]:
        """Read actual output power"""
        with psu_lock:
            try:
                raw = self.psu.read_register(0x0003)
                return raw * 0.1
            except Exception as e:
                print(f"✗ Failed to read power: {e}")
                return None
    
    def get_all_status(self) -> Optional[Dict]:
        """Read all PSU status registers"""
        with psu_lock:
            try:
                raw_values = self.psu.read_registers(0x0001, 13)
                
                status = {
                    'voltage': raw_values[0] * 0.1,
                    'current': raw_values[1] * 0.1,
                    'power': raw_values[2] * 0.1,
                    'capacity': raw_values[3] * 0.1,
                    'runtime': raw_values[4],
                    'battery_v': raw_values[5] * 0.1,
                    'sys_fault': raw_values[6],
                    'mod_fault': raw_values[7],
                    'temperature': raw_values[8],
                    'status': raw_values[9],
                    'set_voltage_rb': raw_values[10] * 0.1,
                    'set_current_rb': raw_values[11] * 0.1,
                    'output_enable': raw_values[12]
                }
                return status
            
            except Exception as e:
                print(f"✗ Failed to read PSU status: {e}")
                return None
    
    def is_device_online(self) -> bool:
        """Check if PSU is accessible"""
        try:
            self.psu.read_register(0x0001)
            return True
        except Exception:
            return False


# Convenience functions for direct use
_client = None

def get_client() -> PSUClient:
    """Get or create PSU client instance"""
    global _client
    if _client is None:
        _client = PSUClient()
    return _client


def set_voltage_current(voltage: float, current: float) -> bool:
    """Set voltage and current (convenience function)"""
    return get_client().set_voltage_current(voltage, current)


def set_voltage(voltage: float) -> bool:
    """Set voltage (convenience function)"""
    return get_client().set_voltage(voltage)


def set_current(current: float) -> bool:
    """Set current (convenience function)"""
    return get_client().set_current(current)


def enable_output() -> bool:
    """Enable output (convenience function)"""
    return get_client().enable_output()


def disable_output() -> bool:
    """Disable output (convenience function)"""
    return get_client().disable_output()


def safe_shutdown() -> bool:
    """Safe shutdown (convenience function)"""
    return get_client().safe_shutdown()


# Test code
if __name__ == "__main__":
    print("PSU Control Test")
    print()
    
    client = PSUClient()
    
    # Check device
    if not client.is_device_online():
        print("✗ PSU not found")
        exit(1)
    
    print(f"✓ Found PSU on {client.com_port}")
    print()
    
    # Read current status
    status = client.get_all_status()
    if status:
        print(f"Current state:")
        print(f"  Voltage: {status['voltage']:.1f}V")
        print(f"  Current: {status['current']:.1f}A")
        print(f"  Power: {status['power']:.1f}W")
        print(f"  Output: {'ON' if status['output_enable'] else 'OFF'}")
        print()
    
    # Test set command
    print("Testing: Set 150V, 5A (should enable output)")
    if client.set_voltage_current(150.0, 5.0):
        time.sleep(1)
        v = client.get_voltage()
        i = client.get_current()
        print(f"  Actual: {v:.1f}V, {i:.1f}A")
    
    print()
    print("Safe shutdown...")
    client.safe_shutdown()
    print("✓ Done")

