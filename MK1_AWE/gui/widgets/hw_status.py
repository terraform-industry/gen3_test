"""Hardware status indicators widget"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QThread, Signal
from concurrent.futures import ThreadPoolExecutor, as_completed
import nidaqmx.system
import ctypes
import requests

try:
    from ..config_loader import load_config
    from ..bga_client import is_bridge_available
except ImportError:
    from config_loader import load_config
    from bga_client import is_bridge_available


class StatusWorker(QThread):
    """Background worker for checking hardware status"""
    status_updated = Signal(dict)
    
    def run(self):
        """Check all Gen3 devices in parallel and emit results"""
        results = {}
        
        # Load config
        try:
            config = load_config()
        except Exception as e:
            print(f"Error loading config: {e}")
            self.status_updated.emit(results)
            return
        
        # Check NI cDAQ (both analog and relay)
        try:
            device_name = config['devices']['NI_cDAQ']['name']
            results['AIM'] = self._check_ni_cdaq(device_name)  # Analog Input Module
            results['RLM'] = results['AIM']  # Same device, Relay Logic Module
        except Exception:
            results['AIM'] = False
            results['RLM'] = False
        
        # Check Pico TC-08
        try:
            dll_path = config['devices']['Pico_TC08']['dll_path']
            results['TCM'] = self._check_pico_tc08(dll_path)  # Thermocouple Module
        except Exception:
            results['TCM'] = False
        
        # Check BGAs via HTTP bridges
        try:
            bga_ports = config['bridges']
            results['BGA01'] = is_bridge_available(bga_ports['bga01']['port'], timeout=0.5)
            results['BGA02'] = is_bridge_available(bga_ports['bga02']['port'], timeout=0.5)
            results['BGA03'] = is_bridge_available(bga_ports['bga03']['port'], timeout=0.5)
        except Exception:
            results['BGA01'] = False
            results['BGA02'] = False
            results['BGA03'] = False
        
        # PSU - on hold for now
        results['PSU'] = False
        
        self.status_updated.emit(results)
    
    def _check_ni_cdaq(self, device_name):
        """Check if NI cDAQ is accessible"""
        try:
            system = nidaqmx.system.System.local()
            device_names = [device.name for device in system.devices]
            return device_name in device_names
        except Exception:
            return False
    
    def _check_pico_tc08(self, dll_path):
        """Check if Pico TC-08 is accessible"""
        try:
            dll = ctypes.WinDLL(dll_path)
            dll.usb_tc08_open_unit.restype = ctypes.c_int16
            handle = dll.usb_tc08_open_unit()
            if handle > 0:
                dll.usb_tc08_close_unit.argtypes = [ctypes.c_int16]
                dll.usb_tc08_close_unit(handle)
                return True
            return False
        except Exception:
            return False


class HardwareStatusWidget(QWidget):
    hardware_status_changed = Signal(dict)
    
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Create status indicators
        self.status_labels = {}
        device_names = ['AIM', 'RLM', 'TCM', 'BGA01', 'BGA02', 'BGA03', 'PSU']
        
        for name in device_names:
            indicator = self._create_status_indicator(name)
            self.status_labels[name] = indicator
            layout.addWidget(indicator)
        
        layout.addStretch()
        
        # Apply styling
        self.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #e0e0e0;
                padding: 5px 10px;
                border-radius: 4px;
                background-color: #4a4a4a;
            }
        """)
        
        # Background worker
        self.worker = None
    
    def _create_status_indicator(self, name):
        """Create a single status indicator label"""
        label = QLabel(f"● {name}: Unknown")
        label.setProperty("device", name)
        label.setProperty("status", "unknown")
        self._update_indicator_style(label, "unknown")
        return label
    
    def _update_indicator_style(self, label, status):
        """Update indicator color based on status"""
        colors = {
            "online": "#4CAF50",   # Green
            "offline": "#F44336",  # Red
            "unknown": "#9E9E9E"   # Gray
        }
        color = colors.get(status, colors["unknown"])
        
        label.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                color: {color};
                padding: 5px 10px;
                border-radius: 4px;
                background-color: #4a4a4a;
                font-weight: bold;
            }}
        """)
    
    def update_status(self):
        """Start background check of hardware status (non-blocking)"""
        # Don't start new check if one is already running
        if self.worker and self.worker.isRunning():
            return
        
        self.worker = StatusWorker()
        self.worker.status_updated.connect(self._apply_status_results)
        self.worker.start()
    
    def _apply_status_results(self, results):
        """Apply status results to UI (runs in main thread)"""
        # AIM (NI cDAQ Analog)
        status = "online" if results.get('AIM', False) else "offline"
        self.status_labels['AIM'].setText(f"● AIM: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['AIM'], status)
        
        # RLM (NI cDAQ Relays)
        status = "online" if results.get('RLM', False) else "offline"
        self.status_labels['RLM'].setText(f"● RLM: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['RLM'], status)
        
        # TCM (Pico TC-08)
        status = "online" if results.get('TCM', False) else "offline"
        self.status_labels['TCM'].setText(f"● TCM: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['TCM'], status)
        
        # BGA01
        status = "online" if results.get('BGA01', False) else "offline"
        self.status_labels['BGA01'].setText(f"● BGA01: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['BGA01'], status)
        
        # BGA02
        status = "online" if results.get('BGA02', False) else "offline"
        self.status_labels['BGA02'].setText(f"● BGA02: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['BGA02'], status)
        
        # BGA03
        status = "online" if results.get('BGA03', False) else "offline"
        self.status_labels['BGA03'].setText(f"● BGA03: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['BGA03'], status)
        
        # PSU
        status = "online" if results.get('PSU', False) else "offline"
        self.status_labels['PSU'].setText(f"● PSU: {'Online' if status == 'online' else 'Offline'}")
        self._update_indicator_style(self.status_labels['PSU'], status)
        
        # Emit signal for hardware availability changes
        self.hardware_status_changed.emit(results)

