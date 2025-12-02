"""Main window for MK1_AWE Control GUI"""

import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QFrame, QStatusBar, QDialog, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from widgets.hw_status import HardwareStatusWidget
from widgets.relay_panel import RelayPanel
from widgets.bga_panel import BGAPanel
from widgets.psu_panel import PSUPanel
from widgets.export_dialog import ExportDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Set window title
        self.setWindowTitle("Gen3 AWE Control App")
        self.setMinimumSize(1000, 700)
        
        # Track which devices have been initialized to safe state
        self.initialized_devices = set()
        
        # Track previous hardware status to detect disconnections
        self.previous_status = {}
        
        # Flag to suppress popups during shutdown
        self.is_shutting_down = False
        
        # Apply modern stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QFrame {
                background-color: #3c3c3c;
                border-radius: 8px;
                padding: 15px;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
            }
            QStatusBar {
                background-color: #252525;
                color: #888888;
            }
        """)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Top row: Hardware status (left) + BGA Purge (middle) + PSU (right)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)
        
        # Hardware status indicators (vertical column)
        self.hw_status_widget = HardwareStatusWidget()
        top_layout.addWidget(self.hw_status_widget, 0)  # Don't expand
        
        # BGA Purge control
        self.bga_panel = BGAPanel()
        self.bga_panel.setMaximumWidth(300)
        top_layout.addWidget(self.bga_panel, 0)
        
        # PSU Settings
        self.psu_panel = PSUPanel()
        top_layout.addWidget(self.psu_panel, 1)  # Expand to fill
        
        main_layout.addLayout(top_layout)
        
        # Relay panel
        self.relay_panel = RelayPanel()
        main_layout.addWidget(self.relay_panel, 1)
        
        # Connect hardware status changes to control panel availability
        self.hw_status_widget.hardware_status_changed.connect(self._update_control_availability)
        
        # Connect save button from hardware status widget
        self.hw_status_widget.save_clicked.connect(self._on_save_clicked)
        
        # Connect purge button to relay panel (update button states)
        self.bga_panel.purge_relays_changed.connect(self.relay_panel.set_purge_valves)
        
        # Start background worker to refresh status every 5 seconds
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.hw_status_widget.update_status)
        self.status_timer.start(5000)  # 5 seconds
        
        # Trigger first status check (non-blocking)
        self.hw_status_widget.update_status()
        
        # Launch cameras
        self._launch_cameras()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)
    
    def _update_control_availability(self, status_results):
        """Update control panel availability based on hardware status"""
        # Check for disconnections and show alerts (unless shutting down)
        if not self.is_shutting_down:
            self._check_for_disconnections(status_results)
        
        # Relay panel: enabled if RLM is online
        rlm_online = status_results.get('RLM', False)
        self.relay_panel.set_hardware_available(rlm_online)
        
        # Initialize RLM to safe state on first connection
        if rlm_online and 'RLM' not in self.initialized_devices:
            self.relay_panel.set_all_off()
            self.initialized_devices.add('RLM')
        elif not rlm_online and 'RLM' in self.initialized_devices:
            self.initialized_devices.discard('RLM')
        
        # Purge panel: enabled when RLM online (controls purge relays RL04, RL06)
        self.bga_panel.set_hardware_available(rlm_online)
        
        # Initialize purge to safe state on first RLM connection
        if rlm_online and 'PURGE' not in self.initialized_devices:
            self.bga_panel.set_normal_mode()  # Close purge valves
            self.initialized_devices.add('PURGE')
        elif not rlm_online and 'PURGE' in self.initialized_devices:
            self.initialized_devices.discard('PURGE')
        
        # Initialize BGAs to normal gases on first connection
        bga1_online = status_results.get('BGA01', False)
        bga2_online = status_results.get('BGA02', False)
        bga3_online = status_results.get('BGA03', False)
        bgas_online = bga1_online or bga2_online or bga3_online
        
        if bgas_online and 'BGA' not in self.initialized_devices:
            self.bga_panel.initialize_bgas()
            self.initialized_devices.add('BGA')
        elif not bgas_online and 'BGA' in self.initialized_devices:
            self.initialized_devices.discard('BGA')
        
        # PSU panel: Enable when PSU online
        psu_online = status_results.get('PSU', False)
        psu_count = 1 if psu_online else 0
        self.psu_panel.set_hardware_available(psu_count)
        
        # Track PSU connection (but don't auto-initialize - user controls it)
        if psu_online and 'PSU' not in self.initialized_devices:
            self.initialized_devices.add('PSU')
            print("PSU online - user can control via GUI")
        elif not psu_online and 'PSU' in self.initialized_devices:
            self.initialized_devices.discard('PSU')
        
        # Store current status for next comparison
        self.previous_status = status_results.copy()
    
    def _check_for_disconnections(self, current_status):
        """Detect hardware disconnections and show alert"""
        if not self.previous_status:
            return
        
        disconnected = []
        
        # Check all Gen3 devices
        for device in ['AIM', 'RLM', 'TCM', 'BGA01', 'BGA02', 'BGA03', 'PSU']:
            was_online = self.previous_status.get(device, False)
            is_online = current_status.get(device, False)
            if was_online and not is_online:
                disconnected.append(device)
        
        # Show alert for disconnections
        if disconnected:
            devices_str = ', '.join(disconnected)
            self._show_disconnect_alert(devices_str)
            print(f"Hardware disconnected: {devices_str}")
    
    def _show_disconnect_alert(self, devices_str):
        """Show styled disconnect alert dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Hardware Disconnected")
        dialog.setModal(False)  # Non-blocking
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Message label
        message = QLabel(f"{devices_str} is offline")
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)
        
        # OK button
        ok_button = QPushButton("Okay")
        ok_button.setMinimumHeight(40)
        ok_button.clicked.connect(dialog.close)
        layout.addWidget(ok_button)
        
        # Apply styling to match main GUI
        dialog.setStyleSheet("""
            QDialog {
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
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)
        
        dialog.show()
    
    def closeEvent(self, event):
        """Handle window close - return all systems to safe state"""
        self.is_shutting_down = True
        self.status_bar.showMessage("Shutting down safely...")
        
        # Close cameras
        self._close_cameras()
        
        # Stop background status checks
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
        
        # Wait for status worker to finish if running
        if hasattr(self.hw_status_widget, 'worker') and self.hw_status_widget.worker:
            if self.hw_status_widget.worker.isRunning():
                self.hw_status_widget.worker.wait(1000)  # Wait up to 1 second
        
        # PSU safe state
        if 'PSU' in self.initialized_devices:
            try:
                from psu_rtu_client import safe_shutdown
                safe_shutdown()
                print("PSU set to safe state (0V, 0A, OFF)")
            except Exception as e:
                print(f"Error setting PSU to safe state: {e}")
        
        # Return relays to safe state
        if 'RLM' in self.initialized_devices:
            try:
                self.relay_panel.set_all_off()
            except Exception as e:
                print(f"Error setting RLM to safe state on shutdown: {e}")
        
        # Return BGAs to normal gases
        if 'BGA' in self.initialized_devices:
            try:
                self.bga_panel.initialize_bgas()
            except Exception as e:
                print(f"Error setting BGAs to normal on shutdown: {e}")
        
        # Close purge valves
        if 'PURGE' in self.initialized_devices:
            try:
                self.bga_panel.set_normal_mode()
            except Exception as e:
                print(f"Error closing purge valves on shutdown: {e}")
        
        print("Safe shutdown complete")
        event.accept()
    
    def _on_save_clicked(self):
        """Open export dialog"""
        dialog = ExportDialog(self)
        dialog.export_requested.connect(self._run_export)
        dialog.exec()
    
    def _run_export(self):
        """Execute data export as subprocess"""
        import subprocess
        from pathlib import Path
        
        self.status_bar.showMessage("Exporting data...")
        
        try:
            # Run process_test.py script
            script_path = Path(__file__).parent.parent / "data" / "process_test.py"
            python_exe = Path(sys.executable)
            
            # Run in subprocess
            result = subprocess.run(
                [str(python_exe), str(script_path)],
                capture_output=True,
                text=True,
                cwd=script_path.parent
            )
            
            if result.returncode == 0:
                self.status_bar.showMessage("Export complete!", 5000)
                self._show_info("Export Complete", 
                              "Data exported and plots generated successfully!\n\n"
                              "Check MK1_AWE/data/ folder for output.")
            else:
                self.status_bar.showMessage("Export failed", 5000)
                self._show_error("Export Failed", 
                               f"Error during export:\n{result.stderr[:500]}")
        
        except Exception as e:
            self.status_bar.showMessage("Export error", 5000)
            self._show_error("Export Error", f"Failed to run export:\n{e}")
    
    def _show_info(self, title, message):
        """Show styled info dialog"""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(QMessageBox.Information)
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
    
    def _show_error(self, title, message):
        """Show styled error dialog"""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(QMessageBox.Warning)
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
    
    def _launch_cameras(self):
        """Launch camera streams via start_cameras.bat"""
        import subprocess
        from pathlib import Path
        
        try:
            camera_script = Path(__file__).parent.parent.parent / "cameras" / "start_cameras.bat"
            if camera_script.exists():
                subprocess.Popen([str(camera_script)], shell=True)
                print("Camera streams launched")
        except Exception as e:
            print(f"Error launching cameras: {e}")
    
    def _close_cameras(self):
        """Close all VLC windows"""
        import subprocess
        
        try:
            # Kill all VLC processes
            subprocess.run(["taskkill", "/F", "/IM", "vlc.exe"], 
                         capture_output=True, check=False)
            print("Camera streams closed")
        except Exception as e:
            print(f"Error closing cameras: {e}")
    
    def _create_placeholder_frame(self, label_text):
        """Create a styled placeholder frame with label"""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        
        layout = QVBoxLayout(frame)
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold; font-size: 16px; color: #888888;")
        layout.addWidget(label)
        
        return frame

