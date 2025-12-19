"""BGA Purge control panel widget"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal

try:
    from ..config_loader import load_config, get_psu_config, load_sensor_labels
    from ..bga_client import set_secondary_gas
except ImportError:
    from config_loader import load_config, get_psu_config, load_sensor_labels
    from bga_client import set_secondary_gas


class BGAPanel(QWidget):
    purge_relays_changed = Signal(bool)  # Signal when purge relays change (RL04, RL06)
    
    def __init__(self):
        super().__init__()
        
        # Check if Gen2 mode (purge valves needed)
        psu_config = get_psu_config()
        self.is_gen2 = (psu_config.get('mode') == 'gen2')
        
        # Load BGA gas configuration from sensor_labels.yaml
        labels = load_sensor_labels()
        bgas = labels.get('bgas', {})
        self.bga01_gases = bgas.get('BGA01', {}).get('gases', {'primary': '1333-74-0', 'secondary': '7782-44-7', 'purge': '7727-37-9'})
        self.bga02_gases = bgas.get('BGA02', {}).get('gases', {'primary': '7782-44-7', 'secondary': '1333-74-0', 'purge': '7727-37-9'})
        self.bga03_gases = bgas.get('BGA03', {}).get('gases', self.bga01_gases)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Purge button (controls RL04, RL06)
        self.purge_button = QPushButton("PURGE")
        self.purge_button.setCheckable(True)
        self.purge_button.setEnabled(False)  # Disabled until RLM connects
        self.purge_button.setMinimumHeight(100)
        self.purge_button.clicked.connect(self._toggle_purge)
        layout.addWidget(self.purge_button)
        
        layout.addStretch()
        
        # Apply styling
        self.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666666;
            }
            QPushButton:checked {
                background-color: #FF9800;
                color: #000000;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #666666;
                border: 2px dashed #444444;
            }
        """)
    
    def _toggle_purge(self, checked):
        """Toggle purge relays (RL04 O2 Purge, RL06 H2 Purge)"""
        # Import relay client
        try:
            from ..ni_relay_client import set_relay
        except ImportError:
            from ni_relay_client import set_relay
        
        try:
            # Control purge relays
            set_relay('RL04', checked)  # O2 Purge
            set_relay('RL06', checked)  # H2 Purge
            
            # Emit signal so relay panel can update button states
            self.purge_relays_changed.emit(checked)
            
            print(f"Purge valves: {'OPEN' if checked else 'CLOSED'} (RL04, RL06)")
        
        except Exception as e:
            print(f"Error toggling purge: {e}")
            # Revert button on error
            self.purge_button.setChecked(not checked)
    
    def set_hardware_available(self, rlm_online):
        """Enable/disable purge button based on RLM (relay) availability"""
        # Enable if relays are online (controls RL02, RL04)
        self.purge_button.setEnabled(rlm_online)
    
    def initialize_bgas(self):
        """Initialize all BGAs to normal gas configuration (safe state)"""
        import time
        
        # Import BGA client
        try:
            from ..bga_client import set_primary_gas, set_secondary_gas
        except ImportError:
            from bga_client import set_primary_gas, set_secondary_gas
        
        success_count = 0
        
        # BGA01
        try:
            set_primary_gas('BGA01', self.bga01_gases['primary'])
            time.sleep(0.05)
            set_secondary_gas('BGA01', self.bga01_gases['secondary'])
            time.sleep(0.05)
            success_count += 1
        except Exception as e:
            print(f"  BGA01 init failed: {e}")
        
        # BGA02
        try:
            set_primary_gas('BGA02', self.bga02_gases['primary'])
            time.sleep(0.05)
            set_secondary_gas('BGA02', self.bga02_gases['secondary'])
            time.sleep(0.05)
            success_count += 1
        except Exception as e:
            print(f"  BGA02 init failed: {e}")
            
        # BGA03
        try:
            set_primary_gas('BGA03', self.bga03_gases['primary'])
                time.sleep(0.05)
            set_secondary_gas('BGA03', self.bga03_gases['secondary'])
            success_count += 1
        except Exception as e:
            print(f"  BGA03 init failed: {e}")
        
        if success_count > 0:
            print(f"BGAs initialized to normal configuration ({success_count}/3 successful)")
    
    def set_normal_mode(self):
        """Set purge to safe state (valves closed)"""
        try:
            # Import relay client
            try:
                from ..ni_relay_client import set_relay
            except ImportError:
                from ni_relay_client import set_relay
            
            # Close purge valves
            set_relay('RL04', False)  # O2 Purge closed
            set_relay('RL06', False)  # H2 Purge closed
            
            # Reset button to unchecked
            self.purge_button.setChecked(False)
            
            print("Purge valves set to safe state (CLOSED)")
        except Exception as e:
            print(f"Error setting purge to safe state: {e}")

