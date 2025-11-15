#!/usr/bin/env python3
"""
PSU Control Client (HTTP-based)
Controls single PSU via HTTP bridge to avoid COM port conflicts
"""

import requests
import yaml
import threading
from pathlib import Path
from typing import Optional, Dict

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "config" / "devices.yaml"
PSU_BRIDGE_URL = "http://localhost:8883"

# Safety limits
VOLTAGE_MIN = 100.0  # V
VOLTAGE_MAX = 900.0  # V
CURRENT_MIN = 1.0    # A
CURRENT_MAX = 100.0  # A

# Global lock for thread safety
psu_lock = threading.Lock()


class PSUClient:
    """Client for controlling PSU via HTTP bridge"""
    
    def __init__(self):
        self.bridge_url = PSU_BRIDGE_URL
    
    def _send_command(self, cmd_data):
        """Send command to PSU bridge"""
        try:
            response = requests.post(
                f"{self.bridge_url}/command",
                json=cmd_data,
                timeout=2.0
            )
            if response.status_code == 200:
                return True
            else:
                data = response.json()
                print(f"✗ Command failed: {data.get('error', 'Unknown error')}")
                return False
        except requests.exceptions.Timeout:
            print("✗ Command timeout")
            return False
        except Exception as e:
            print(f"✗ Command error: {e}")
            return False
    
    def _read_status(self):
        """Read current PSU status from bridge"""
        try:
            response = requests.get(f"{self.bridge_url}/metrics", timeout=1.0)
            if response.status_code == 200:
                # Parse InfluxDB line protocol (simple extraction)
                text = response.text.strip()
                if not text or text.startswith('#'):
                    return None
                
                # Extract values from line protocol
                parts = text.split(' ')
                if len(parts) >= 2:
                    fields = parts[1].split(',')
                    data = {}
                    for field in fields:
                        key, val = field.split('=')
                        try:
                            data[key] = float(val)
                        except:
                            data[key] = val
                    return data
            return None
        except Exception:
            return None
    
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
            # Apply safety limits
            if voltage < VOLTAGE_MIN or current < CURRENT_MIN:
                # Below minimum → safe state (0V, 0A, OFF)
                print(f"Below safety limits → Setting safe state (0V, 0A, OFF)")
                voltage = 0.0
                current = 0.0
                enable = 0
            else:
                # Clamp to max limits
                voltage = min(voltage, VOLTAGE_MAX)
                current = min(current, CURRENT_MAX)
                enable = 1
            
            # Send command to bridge
            cmd_data = {
                'type': 'set_voltage_current',
                'voltage': voltage,
                'current': current,
                'enable': enable
            }
            
            if self._send_command(cmd_data):
                print(f"✓ PSU set: {voltage:.1f}V, {current:.1f}A, {'ON' if enable else 'OFF'}")
                return True
            else:
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
            cmd_data = {'type': 'enable'}
            if self._send_command(cmd_data):
                print("✓ PSU output enabled")
                return True
            return False
    
    def disable_output(self) -> bool:
        """Disable PSU output"""
        with psu_lock:
            cmd_data = {'type': 'disable'}
            if self._send_command(cmd_data):
                print("✓ PSU output disabled")
                return True
            return False
    
    def safe_shutdown(self) -> bool:
        """Set PSU to safe state: 0V, 0A, output OFF"""
        return self.set_voltage_current(0.0, 0.0)
    
    def get_voltage(self) -> Optional[float]:
        """Read actual output voltage"""
        data = self._read_status()
        return data.get('voltage') if data else None
    
    def get_current(self) -> Optional[float]:
        """Read actual output current"""
        data = self._read_status()
        return data.get('current') if data else None
    
    def get_power(self) -> Optional[float]:
        """Read actual output power"""
        data = self._read_status()
        return data.get('power') if data else None
    
    def get_all_status(self) -> Optional[Dict]:
        """Read all PSU status"""
        return self._read_status()
    
    def is_device_online(self) -> bool:
        """Check if PSU bridge is accessible"""
        try:
            response = requests.get(f"{self.bridge_url}/health", timeout=1.0)
            if response.status_code == 200:
                data = response.json()
                return data.get('device_online', False)
            return False
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
    import time
    
    print("PSU Control Test (via HTTP bridge)")
    print("Make sure psu_http.py bridge is running!")
    print()
    
    client = PSUClient()
    
    # Check device
    if not client.is_device_online():
        print("✗ PSU bridge not responding")
        print("  Start bridge: python MK1_AWE/hdw/psu_http.py")
        exit(1)
    
    print(f"✓ PSU bridge online")
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
        time.sleep(2)
        v = client.get_voltage()
        i = client.get_current()
        if v and i:
            print(f"  Actual: {v:.1f}V, {i:.1f}A")
    
    print()
    print("Safe shutdown...")
    client.safe_shutdown()
    print("✓ Done")

