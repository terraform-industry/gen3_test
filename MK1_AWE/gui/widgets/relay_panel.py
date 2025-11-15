"""Relay control panel widget"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QPushButton, QGridLayout, QMessageBox
from PySide6.QtCore import Qt, Signal

try:
    from ..config_loader import load_config
    from ..ni_relay_client import set_relay, set_all_relays
except ImportError:
    from config_loader import load_config
    from ni_relay_client import set_relay, set_all_relays


class RelayPanel(QWidget):
    contactor_state_changed = Signal(bool)  # Kept for compatibility (unused in Gen3)
    
    def __init__(self):
        super().__init__()
        
        # Store all buttons for enable/disable
        self.all_buttons = []
        self.current_setpoint = 0.0  # Track PSU current (unused for now)
        
        # Load relay configuration
        config = load_config()
        relay_config = config['modules']['NI_cDAQ_Relays']
        
        # Combine all relays from both slots
        all_relays = {}
        all_relays.update(relay_config['slot_2'])
        all_relays.update(relay_config['slot_3'])
        
        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Single relay group (all 16 relays)
        relay_group = self._create_relay_group("Relays", all_relays)
        main_layout.addWidget(relay_group)
        
        # Apply styling
        self.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #e0e0e0;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px;
                background-color: #3c3c3c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 5px 10px;
                background-color: #2b2b2b;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #555555;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #666666;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555555;
                border: 2px dashed #444444;
            }
        """)
    
    def _create_relay_group(self, title, relays):
        """Create a group box with relay buttons"""
        group = QGroupBox(title)
        layout = QGridLayout()
        layout.setSpacing(10)
        
        # Sort relays by name (RL01, RL02, ...)
        sorted_relays = sorted(relays.items(), key=lambda x: x[0])
        
        # Create buttons in grid (4 columns for 16 relays = 4x4 grid)
        for idx, (relay_id, relay_info) in enumerate(sorted_relays):
            row = idx // 4
            col = idx % 4
            
            button = QPushButton(relay_info['name'])
            button.setCheckable(True)
            button.setEnabled(False)  # Disabled until RLM connects
            button.setProperty("relay_id", relay_id)
            
            # Connect to toggle handler
            button.clicked.connect(lambda checked, rid=relay_id: self._toggle_relay(rid, checked))
            
            layout.addWidget(button, row, col)
            self.all_buttons.append(button)
        
        group.setLayout(layout)
        return group
    
    def set_hardware_available(self, available):
        """Enable/disable relay controls based on RLM availability"""
        for button in self.all_buttons:
            button.setEnabled(available)
    
    def set_all_off(self):
        """Turn all relays OFF (safe state)"""
        try:
            set_all_relays(False)
            for button in self.all_buttons:
                button.setChecked(False)
            print("All relays set to OFF (safe state)")
        except Exception as e:
            print(f"Error setting relays to safe state: {e}")
    
    def set_psu_current(self, amps):
        """Update PSU current setpoint (kept for compatibility)"""
        self.current_setpoint = amps
    
    def set_purge_valves(self, purge_active):
        """Unlinked from relays - kept for compatibility"""
        pass
    
    def _toggle_relay(self, relay_id, state):
        """Toggle relay via NI-DAQmx"""
        try:
            set_relay(relay_id, state)
        except Exception as e:
            print(f"Error toggling relay {relay_id}: {e}")
    
    def _show_interlock_warning(self, title, message):
        """Show styled interlock warning dialog"""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
            }
            QPushButton {
                background-color: #555555;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 14px;
            }
        """)
        msg.exec()

