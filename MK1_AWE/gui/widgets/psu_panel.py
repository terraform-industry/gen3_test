"""PSU control panel widget"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFormLayout, QMessageBox, QProgressBar
)
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt, Signal, QTimer

try:
    from ..psu_client import set_current, stop, get_max_current, get_ramp_config, load_profile
    from ..config_loader import get_psu_config
except ImportError:
    from psu_client import set_current, stop, get_max_current, get_ramp_config, load_profile
    from config_loader import get_psu_config

import time


class PSUPanel(QWidget):
    current_changed = Signal(float)  # Signal when current setpoint changes
    
    def __init__(self):
        super().__init__()
        
        # Track contactor state for interlock
        self.contactor_closed = False
        self.psu_available = False
        self.current_setpoint = 0.0
        self.is_ramping = False
        self.is_profiling = False
        
        # Profile/ramp execution state
        self.profile_data = None
        self.profile_index = 0
        self.profile_timer = None
        self.profile_voltage = None
        self.ramp_voltage = None
        self.operation_start_time = None
        self.operation_total_duration = None
        
        # Get PSU mode
        psu_config = get_psu_config()
        self.mode = psu_config['mode']
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Power Settings")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        layout.addWidget(title)
        
        # Input fields (mode-aware)
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        if self.mode == 'gen3':
            # Gen3: Voltage and Current for single PSU
            self.voltage_input = QLineEdit()
            self.voltage_input.setPlaceholderText("100 - 900")
            self.voltage_input.setValidator(QDoubleValidator(0.0, 900.0, 1))
            form_layout.addRow("Voltage (V):", self.voltage_input)
            
            self.current_input = QLineEdit()
            self.current_input.setPlaceholderText("1 - 100")
            self.current_input.setValidator(QDoubleValidator(0.0, 100.0, 1))
            form_layout.addRow("Current (A):", self.current_input)
        elif self.mode == 'mk1':
            # MK1: Voltage and Current
            self.voltage_input = QLineEdit()
            self.voltage_input.setPlaceholderText("100 - 300")
            self.voltage_input.setValidator(QDoubleValidator(0.0, 300.0, 1))
            form_layout.addRow("Voltage (V):", self.voltage_input)
            
            self.current_input = QLineEdit()
            self.current_input.setPlaceholderText("1 - 100")
            self.current_input.setValidator(QDoubleValidator(0.0, 100.0, 1))
            form_layout.addRow("Current (A):", self.current_input)
        else:
            # Gen2: Current only
            self.voltage_input = None
            
            self.current_input = QLineEdit()
            self.current_input.setPlaceholderText("0 - 100")
            self.current_input.setValidator(QDoubleValidator(0.0, 100.0, 1))
            form_layout.addRow("Current (A):", self.current_input)
        
        layout.addLayout(form_layout)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Enter button
        self.enter_button = QPushButton("ENTER")
        self.enter_button.setEnabled(False)
        self.enter_button.setMinimumHeight(50)
        self.enter_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.enter_button)
        
        # Ramp button (both modes)
        self.ramp_button = QPushButton("RAMP")
        self.ramp_button.setEnabled(False)
        self.ramp_button.setMinimumHeight(50)
        self.ramp_button.clicked.connect(self._start_ramp)
        button_layout.addWidget(self.ramp_button)
        
        # Profile button (both modes)
        self.profile_button = QPushButton("PROFILE")
        self.profile_button.setEnabled(False)
        self.profile_button.setMinimumHeight(50)
        self.profile_button.clicked.connect(self._start_profile)
        button_layout.addWidget(self.profile_button)
        
        # Stop button
        self.stop_button = QPushButton("STOP")
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumHeight(50)
        self.stop_button.clicked.connect(self._stop_all)
        button_layout.addWidget(self.stop_button)
        
        layout.addLayout(button_layout)
        
        # Progress bar and status
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(20)
        progress_layout.addWidget(self.progress_bar, 1)
        
        self.progress_label = QLabel("")
        self.progress_label.setMinimumWidth(150)
        self.progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_layout.addWidget(self.progress_label, 0)
        
        layout.addLayout(progress_layout)
        
        # Timer for continuous time update
        self.progress_update_timer = QTimer()
        self.progress_update_timer.timeout.connect(self._update_progress_display)
        
        layout.addStretch()
        
        # Apply styling
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #4a4a4a;
                color: #e0e0e0;
                border: 2px solid #555555;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
                min-width: 150px;
            }
            QLineEdit:focus {
                border: 2px solid #2196F3;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                opacity: 0.9;
            }
            QPushButton#enter_button {
                background-color: #4CAF50;
                color: #ffffff;
            }
            QPushButton#enter_button:hover {
                background-color: #45a049;
            }
            QPushButton#enter_button:disabled {
                background-color: #333333;
                color: #666666;
            }
            QPushButton#stop_button {
                background-color: #F44336;
                color: #ffffff;
            }
            QPushButton#stop_button:hover {
                background-color: #da190b;
            }
            QPushButton#stop_button:disabled {
                background-color: #333333;
                color: #666666;
            }
            QPushButton#ramp_button {
                background-color: #2196F3;
                color: #ffffff;
            }
            QPushButton#ramp_button:hover {
                background-color: #1976D2;
            }
            QPushButton#ramp_button:disabled {
                background-color: #333333;
                color: #666666;
            }
            QPushButton#profile_button {
                background-color: #9C27B0;
                color: #ffffff;
            }
            QPushButton#profile_button:hover {
                background-color: #7B1FA2;
            }
            QPushButton#profile_button:disabled {
                background-color: #333333;
                color: #666666;
            }
            QProgressBar {
                border: 2px solid #555555;
                border-radius: 4px;
                background-color: #3c3c3c;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 2px;
            }
        """)
        
        # Set object names for styling
        self.enter_button.setObjectName("enter_button")
        self.stop_button.setObjectName("stop_button")
        if self.ramp_button:
            self.ramp_button.setObjectName("ramp_button")
        if self.profile_button:
            self.profile_button.setObjectName("profile_button")
        
        # Initialize button states (start disabled)
        self._update_button_states()
    
    def _apply_settings(self):
        """Apply PSU settings"""
        # Get voltage and current values
        current_text = self.current_input.text()
        if not current_text:
            return
        
        try:
            amps = float(current_text)
            
            if self.mode == 'gen3':
                # Gen3: Get voltage and current, use new PSU client
                voltage_text = self.voltage_input.text() if self.voltage_input else ""
                if not voltage_text:
                    self._show_error("Missing Input", "Please enter voltage")
                    return
                
                volts = float(voltage_text)
                
                # Import Gen3 PSU client
                try:
                    from ..psu_rtu_client import set_voltage_current
                except ImportError:
                    from psu_rtu_client import set_voltage_current
                
                # Set voltage and current (safety limits handled by client)
                if set_voltage_current(volts, amps):
                    print(f"Applied: {volts}V, {amps}A")
                else:
                    self._show_error("Error", "Failed to set PSU")
                    return
                
            elif self.mode == 'mk1':
                # MK1: Also get voltage
                voltage_text = self.voltage_input.text() if self.voltage_input else "120"
                volts = float(voltage_text) if voltage_text else 120.0
                
                # Set voltage and current
                set_current(amps, voltage=volts)
                
                # Enable outputs
                try:
                    from ..psu_client import _enable_output_mk1
                except ImportError:
                    from psu_client import _enable_output_mk1
                
                _enable_output_mk1(True)
                
                print(f"Applied: {volts}V, {amps}A, outputs enabled")
            else:
                # Gen2: Current only
                set_current(amps)
                print(f"Applied: {amps}A")
            
            # Track and emit for interlocks
            self.current_setpoint = amps
            self.current_changed.emit(amps)
            
        except ValueError as e:
            self._show_error("Invalid Input", str(e))
        except ConnectionError as e:
            self._show_error("Connection Error", f"Failed to apply settings:\n{e}")
        except Exception as e:
            self._show_error("Error", f"Failed to apply settings:\n{e}")
    
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
    
    def _update_progress_display(self):
        """Update progress bar and time remaining (called every second)"""
        if not (self.is_ramping or self.is_profiling):
            return
        
        if self.operation_start_time is None:
            return
        
        # Calculate actual elapsed time
        elapsed = time.time() - self.operation_start_time
        
        # For ramping: calculate remaining based on steps
        if self.is_ramping:
            steps_remaining = self.ramp_max_steps - self.ramp_current_step + 1
            remaining = steps_remaining * self.ramp_step_duration
            total = self.ramp_max_steps * self.ramp_step_duration
            percent = min(100, int((elapsed / total) * 100)) if total > 0 else 0
            
        # For profiling: calculate remaining based on current vs last point
        elif self.is_profiling and self.profile_data:
            if self.profile_index < len(self.profile_data):
                current_target_time = self.profile_data[self.profile_index][0]
                last_target_time = self.profile_data[-1][0]
                remaining = last_target_time - current_target_time
                percent = min(100, int((current_target_time / last_target_time) * 100)) if last_target_time > 0 else 0
            else:
                remaining = 0
                percent = 100
        else:
            remaining = 0
            percent = 0
        
        # Update progress bar
        self.progress_bar.setValue(percent)
        
        # Format time remaining as HH:MM:SS
        remaining = max(0, remaining)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        
        if self.is_ramping:
            self.progress_label.setText(f"Ramping | {hours:02d}:{minutes:02d}:{seconds:02d}")
        elif self.is_profiling:
            step_info = f"Step {self.profile_index}/{len(self.profile_data)}" if self.profile_data else ""
            self.progress_label.setText(f"{step_info} | {hours:02d}:{minutes:02d}:{seconds:02d}")
    
    def set_contactor_state(self, closed):
        """Update contactor state for interlock logic"""
        self.contactor_closed = closed
        self._update_button_states()
    
    def set_hardware_available(self, psu_count):
        """Enable/disable PSU controls based on PSU availability"""
        # Enable if at least one PSU is online
        self.psu_available = psu_count > 0
        
        # Enable inputs
        if self.voltage_input:
            self.voltage_input.setEnabled(self.psu_available)
        self.current_input.setEnabled(self.psu_available)
        
        # Update button states
        self._update_button_states()
    
    def _update_button_states(self):
        """Update Enter/Stop/Ramp/Profile button states based on interlocks"""
        # Gen3: No contactor interlock, only PSU availability
        if self.mode == 'gen3':
            interlock_ok = self.psu_available
        else:
            # Gen2/MK1: Requires contactor closed and PSU available
            interlock_ok = self.contactor_closed and self.psu_available
        
        # Enter: Requires interlock OK, not ramping, not profiling
        self.enter_button.setEnabled(interlock_ok and not self.is_ramping and not self.is_profiling)
        
        # Ramp: Requires interlock OK, not ramping, not profiling
        if self.ramp_button:
            self.ramp_button.setEnabled(interlock_ok and not self.is_ramping and not self.is_profiling)
        
        # Profile: Requires interlock OK, not ramping, not profiling
        if self.profile_button:
            self.profile_button.setEnabled(interlock_ok and not self.is_ramping and not self.is_profiling)
        
        # Stop: Enabled if PSU available (to allow emergency stop)
        self.stop_button.setEnabled(self.psu_available)
    
    def _start_ramp(self):
        """Start discrete step ramp from 0A to max current (non-blocking)"""
        # Interlock check (gen2/mk1 only)
        if self.mode != 'gen3' and not self.contactor_closed:
            self._show_interlock_warning(
                "Contactor Open",
                "Cannot ramp while contactor is open.\nClose contactor (RL01) first."
            )
            return
        
        # Get parameters
        num_steps, step_duration = get_ramp_config()
        total_duration = num_steps * step_duration
        
        # Get target current from input field
        current_text = self.current_input.text()
        if not current_text:
            self._show_error("Missing Input", "Please enter target current for ramping")
            return
        
        try:
            target_current = float(current_text)
        except ValueError:
            self._show_error("Invalid Input", "Invalid current value")
            return
        
        max_current = target_current
        
        # MK1: Set voltage to max and enable outputs before ramping
        if self.mode == 'mk1':
            try:
                psu_config = get_psu_config()
                max_voltage = psu_config['mk1']['voltage_max']
                
                try:
                    from ..psu_client import _set_voltage_mk1, _enable_output_mk1
                except ImportError:
                    from psu_client import _set_voltage_mk1, _enable_output_mk1
                
                _set_voltage_mk1(max_voltage)
                _enable_output_mk1(True)
            except Exception as e:
                self._show_error("Ramp Setup Error", f"Failed to prepare PSUs:\n{e}")
                return
        
        # Gen3: Get voltage and current from input fields
        if self.mode == 'gen3':
            voltage_text = self.voltage_input.text() if self.voltage_input else ""
            current_text = self.current_input.text()
            
            if not voltage_text or not current_text:
                self._show_error("Missing Input", "Please enter both voltage and current for ramping")
                return
            
            try:
                self.ramp_voltage = float(voltage_text)
            except ValueError:
                self._show_error("Invalid Input", "Invalid voltage value")
                return
        else:
            self.ramp_voltage = None
        
        # Setup operation tracking
        self.operation_start_time = time.time()
        self.operation_total_duration = total_duration
        self.ramp_current_step = 0
        self.ramp_max_steps = num_steps
        self.ramp_step_duration = step_duration
        self.ramp_max_current = max_current
        
        # Mark as ramping
        self.is_ramping = True
        self._update_button_states()
        
        # Start progress timer (updates every second)
        self.progress_update_timer.start(1000)
        
        # Execute first step immediately
        self._execute_ramp_step()
    
    def _execute_ramp_step(self):
        """Execute one step of the ramp"""
        if not self.is_ramping:
            return
        
        try:
            # Calculate target current for this step
            target_current = (self.ramp_current_step / self.ramp_max_steps) * self.ramp_max_current
            
            # Set current (with voltage for gen3)
            if self.mode == 'gen3' and self.ramp_voltage is not None:
                set_current(target_current, voltage=self.ramp_voltage)
            else:
                set_current(target_current)
            
            self.current_setpoint = target_current
            self.current_changed.emit(target_current)
            
            # Move to next step
            self.ramp_current_step += 1
            
            # Check if ramp complete
            if self.ramp_current_step > self.ramp_max_steps:
                self.current_input.setText(f"{self.ramp_max_current:.1f}")
                print(f"Ramp complete: {self.ramp_max_current}A")
                self._finish_ramp()
                return
            
            # Schedule next step
            self.profile_timer = QTimer()
            self.profile_timer.setSingleShot(True)
            self.profile_timer.timeout.connect(self._execute_ramp_step)
            self.profile_timer.start(self.ramp_step_duration * 1000)
            
        except Exception as e:
            self._show_error("Ramp Error", f"Failed during ramp:\n{e}")
            self._cancel_ramp()
    
    def _cancel_ramp(self):
        """Cancel ongoing ramp"""
        if self.profile_timer:
            self.profile_timer.stop()
            self.profile_timer = None
        
        stop()
        self.current_setpoint = 0.0
        self.current_changed.emit(0.0)
        
        self._finish_ramp()
        print("Ramp cancelled")
    
    def _finish_ramp(self):
        """Clean up after ramp"""
        # MK1: Disable outputs after ramp
        if self.mode == 'mk1':
            try:
                try:
                    from ..psu_client import _enable_output_mk1
                except ImportError:
                    from psu_client import _enable_output_mk1
                
                _enable_output_mk1(False)
            except Exception as e:
                print(f"Warning: Failed to disable PSU outputs: {e}")
        
        # Gen3: Keep output enabled (manual stop required)
        
        self.is_ramping = False
        self.ramp_voltage = None
        self.progress_update_timer.stop()
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self._update_button_states()
    
    def _start_profile(self):
        """Execute current profile from CSV (non-blocking)"""
        # Interlock check (gen2/mk1 only)
        if self.mode != 'gen3' and not self.contactor_closed:
            self._show_interlock_warning(
                "Contactor Open",
                "Cannot run profile while contactor is open.\nClose contactor (RL01) first."
            )
            return
        
        # Load profile
        try:
            self.profile_data = load_profile()
        except FileNotFoundError as e:
            self._show_error("Profile Not Found", str(e))
            return
        except ValueError as e:
            self._show_error("Invalid Profile", str(e))
            return
        except Exception as e:
            self._show_error("Profile Error", f"Failed to load profile:\n{e}")
            return
        
        # Gen3: Get voltage from input field
        if self.mode == 'gen3':
            voltage_text = self.voltage_input.text() if self.voltage_input else ""
            if not voltage_text:
                self._show_error("Missing Input", "Please enter voltage for profile execution")
                return
            try:
                self.profile_voltage = float(voltage_text)
            except ValueError:
                self._show_error("Invalid Input", "Invalid voltage value")
                return
        else:
            self.profile_voltage = None
        
        # MK1: Set voltage to max and enable outputs before profile
        if self.mode == 'mk1':
            try:
                psu_config = get_psu_config()
                max_voltage = psu_config['mk1']['voltage_max']
                
                try:
                    from ..psu_client import _set_voltage_mk1, _enable_output_mk1
                except ImportError:
                    from psu_client import _set_voltage_mk1, _enable_output_mk1
                
                _set_voltage_mk1(max_voltage)
                _enable_output_mk1(True)
            except Exception as e:
                self._show_error("Profile Setup Error", f"Failed to prepare PSUs:\n{e}")
                return
        
        # Setup operation tracking
        self.operation_start_time = time.time()
        self.operation_total_duration = self.profile_data[-1][0]
        self.profile_index = 0
        
        # Mark as profiling
        self.is_profiling = True
        self._update_button_states()
        
        # Start progress timer (updates every second)
        self.progress_update_timer.start(1000)
        
        # Execute first point immediately
        self._execute_profile_step()
    
    def _execute_profile_step(self):
        """Execute one step of the profile (called by timer)"""
        if not self.is_profiling or self.profile_data is None:
            return
        
        try:
            # Get current point
            target_time, target_current = self.profile_data[self.profile_index]
            
            # Set current (with voltage for gen3)
            if self.mode == 'gen3' and self.profile_voltage is not None:
                set_current(target_current, voltage=self.profile_voltage)
            else:
                set_current(target_current)
            
            self.current_setpoint = target_current
            self.current_changed.emit(target_current)
            
            # Progress updates handled by timer
            
            # Move to next point
            self.profile_index += 1
            
            # Check if profile complete
            if self.profile_index >= len(self.profile_data):
                self.current_input.setText(f"{target_current:.1f}")
                print(f"Profile complete: {len(self.profile_data)} points")
                self._finish_profile()
                return
            
            # Schedule next point
            next_time = self.profile_data[self.profile_index][0]
            dt = (next_time - target_time) * 1000  # Convert to milliseconds
            
            self.profile_timer = QTimer()
            self.profile_timer.setSingleShot(True)
            self.profile_timer.timeout.connect(self._execute_profile_step)
            self.profile_timer.start(int(dt))
            
        except Exception as e:
            self._show_error("Profile Error", f"Failed during profile execution:\n{e}")
            self._cancel_profile()
    
    def _cancel_profile(self):
        """Cancel ongoing profile execution"""
        if self.profile_timer:
            self.profile_timer.stop()
            self.profile_timer = None
        
        stop()
        self.current_setpoint = 0.0
        self.current_changed.emit(0.0)
        
        self._finish_profile()
        print("Profile cancelled")
    
    def _finish_profile(self):
        """Clean up after profile execution"""
        # MK1: Disable outputs after profile
        if self.mode == 'mk1':
            try:
                try:
                    from ..psu_client import _enable_output_mk1
                except ImportError:
                    from psu_client import _enable_output_mk1
                
                _enable_output_mk1(False)
            except Exception as e:
                print(f"Warning: Failed to disable PSU outputs: {e}")
        
        # Gen3: Keep output enabled (manual stop required)
        
        self.is_profiling = False
        self.profile_data = None
        self.profile_index = 0
        self.profile_voltage = None
        self.progress_update_timer.stop()
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self._update_button_states()
    
    def _stop_all(self):
        """Stop all PSUs - set to 0A"""
        # Cancel profile if running
        if self.is_profiling:
            self._cancel_profile()
            return
        
        # Cancel ramp if running
        if self.is_ramping:
            self._cancel_ramp()
            return
        
        try:
            # Send stop command to PSU (mode-aware)
            if self.mode == 'gen3':
                try:
                    from ..psu_rtu_client import safe_shutdown
                except ImportError:
                    from psu_rtu_client import safe_shutdown
                safe_shutdown()
            else:
                stop()
            
            # Update tracking
            self.current_setpoint = 0.0
            self.current_changed.emit(0.0)
            self.current_input.clear()
            if self.voltage_input:
                self.voltage_input.clear()
            self.is_ramping = False  # Cancel any ongoing ramp
            self._update_button_states()
            
            print("Stopped: 0V, 0A")
        except Exception as e:
            self._show_error("Error", f"Failed to stop PSU:\n{e}")
    
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

