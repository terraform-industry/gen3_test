# Gen3 AWE Control System – Task List

**Project Goal**: Adapt MK1_AWE monitoring and control system for Gen3 test rig using NI cDAQ-9187, Pico TC-08, single PSU, on Windows platform.

## 📊 Progress Summary

**✅ Phase 1 Complete:** Windows Environment Setup (Tasks 1-10)
**✅ Phase 2 Complete:** Hardware Interfaces (Tasks 11-25, except 19)
**✅ Phase 3 Complete:** Control GUI Implementation (Tasks 26-40)
**✅ Phase 4 Complete:** Grafana Dashboards (Tasks 41-45)
**✅ Phase 3B Complete:** BGA Integration (Tasks 56-61)
**✅ Phase 5 Complete:** Data Export/Analysis (Tasks 46-53)
**🔜 Next:** Final polish and documentation

**System Status:**
- ✅ All hardware bridges running as Windows services (NI analog, Pico TC-08, PSU, BGA01/02/03)
- ✅ Docker stack operational (InfluxDB, Telegraf, Grafana)
- ✅ Data flowing: 16 analog inputs (20Hz) + 8 thermocouples (1Hz) + PSU (10Hz) + 3 BGAs (2Hz)
- ✅ GUI functional: Relay control (16 relays) + PSU control (V/I/Ramp/Profile) + Purge button (RL04/RL06)
- ✅ Grafana dashboards: Analog inputs, Thermocouples, PSU, BGAs, Pressures, Flowrate, Current, Voltage, Power
- ✅ Data export: GUI "Save Data..." button → CSV + plots with sensor labels
- ✅ sensor_labels.yaml: Easy per-test configuration (labels, units, ranges, gas configs)

---

## 🔧 Hardware Configuration

### Target Hardware
- **NI cDAQ-9187** (Ethernet: 192.168.0.108)
  - Slot 1: **NI-9253** (8-channel analog current input, 4-20mA)
  - Slot 2: **NI-9485** (8-channel relay output)
  - Slot 3: **NI-9485** (8-channel relay output)
  - Slot 4: **NI-9253** (8-channel analog current input, 4-20mA)
  - **Total**: 16 analog inputs + 16 relay outputs
- **Pico TC-08**: 8-channel thermocouple logger (USB)
- **3x BGA244**: Binary gas analyzers (RS422/USB adapters)
- **Single PSU**: Modbus RTU via RS485/USB adapter
- **Windows Control Computer**: Brand new, all setup from scratch

### MK1 Reference Hardware (for context)
- Waveshare PoE modules (RLM, TCM, AIM, BGA)
- 10 PSUs via Modbus TCP
- Ubuntu 22.04 host

---

## 📋 Task Roadmap

### Phase 1: Windows Environment Setup (1-10)

1. ✅ **Install Docker Desktop for Windows**
   - Download and install Docker Desktop
   - Enable WSL2 backend
   - Configure resource limits (memory, CPU)
   - Verify with `docker --version` and `docker compose version`

2. ✅ **Install Python 3.11+ for Windows**
   - Download from python.org
   - Add to PATH during installation
   - Install pip
   - Verify with `python --version`

3. ✅ **Install NI-DAQmx drivers**
   - Download NI-DAQmx from ni.com
   - Install runtime and development support
   - Verify device detection in NI MAX (Measurement & Automation Explorer)
   - Test cDAQ-9187 connectivity

4. ✅ **Install Pico SDK and drivers**
   - Download Pico SDK from picotech.com
   - Install USB drivers for TC-08
   - Install PicoLog or SDK libraries
   - Verify TC-08 detection in Device Manager

5. ✅ **Install Git for Windows**
   - Download from git-scm.com
   - Configure user name and email
   - Clone or copy existing repository

6. ✅ **Create Python virtual environment**
   - `python -m venv venv`
   - Activate: `venv\Scripts\activate`
   - Install core dependencies: `pip install PySide6 pyyaml influxdb-client`

7. ✅ **Install Python hardware libraries**
   - NI: `pip install nidaqmx`
   - Pico: `pip install picosdk` or `pip install usbtc08`
   - Modbus RTU: `pip install pymodbus pyserial`

8. ✅ **Setup Windows Defender / Firewall exceptions**
   - Allow Docker ports (8086 InfluxDB, 3000 Grafana, 8888+ bridges)
   - Allow Python application network access
   - Configure localhost exemptions

9. ✅ **Create project directory structure**
   - Copy `docker-compose.yml` to Windows host
   - Create `Gen3_AWE/` folder structure:
     - `config/` (devices.yaml, telegraf.conf, grafana.ini)
     - `gui/` (app.py, clients, widgets)
     - `hdw/` (hardware bridge scripts)
     - `data/` (export and plotting tools)
     - `profiles/` (current profiles CSV)
   - Create `tests/` for hardware validation scripts

10. ✅ **Test basic Docker stack**
    - Start InfluxDB container: `docker compose up -d influxdb`
    - Create org `electrolyzer`, bucket `electrolyzer_data`
    - Generate admin token, save securely
    - Verify InfluxDB UI at http://localhost:8086
    - Stop containers: `docker compose down`

---

### Phase 2: Hardware Interface Development (11-25)

11. ✅ **Test NI cDAQ-9187 connectivity**
    - Use existing test scripts to verify Ethernet connection
    - Detect cDAQ and all installed modules (2x NI-9253, 2x NI-9485)
    - Verify module slot assignments in NI MAX

12. ✅ **Implement NI-9253 analog input reader**
    - Create `Gen3_AWE/hdw/ni_analog_http.py`
    - Read 8 channels (4 per module) at configurable rate (10-100Hz)
    - Scale 4-20mA to engineering units using devices.yaml config
    - Expose `/metrics` endpoint in InfluxDB line protocol
    - Handle errors gracefully (disconnections, out-of-range)

13. ✅ **Implement NI-9485 relay control client**
    - Create `Gen3_AWE/gui/ni_relay_client.py`
    - Functions: `set_relay(slot, channel, state)`, `get_relay_status()`
    - Support 16 relays across 2 modules
    - Include safety checks and state validation

14. ✅ **Test Pico TC-08 connectivity**
    - Use existing test scripts to verify USB connection
    - Detect all 8 thermocouple channels
    - Verify cold junction compensation

15. ✅ **Implement Pico TC-08 reader**
    - Create `Gen3_AWE/hdw/pico_tc08_http.py`
    - Read 8 thermocouple channels at 1Hz (Pico limitation)
    - Support multiple thermocouple types (K, J, T, etc.) from devices.yaml
    - Expose `/metrics` endpoint in InfluxDB line protocol
    - Handle open/failed thermocouples gracefully

16. ✅ **Test PSU Modbus RTU connectivity**
    - Use existing test scripts to verify RS485/USB adapter
    - Identify COM port (e.g., COM3, COM4)
    - Test read/write operations (voltage, current, enable)
    - Document register map

17. ✅ **Implement PSU Modbus RTU client**
    - Create `Gen3_AWE/gui/psu_rtu_client.py`
    - Functions: `set_voltage()`, `set_current()`, `enable_output()`, `disable_output()`
    - Read current PSU state: `get_voltage()`, `get_current()`, `get_power()`
    - Include safety limits and timeout handling

18. ✅ **Implement PSU monitoring bridge**
    - Create `Gen3_AWE/hdw/psu_http.py`
    - Poll PSU at 10Hz for V/I/P/status
    - Expose `/metrics` endpoint for Telegraf
    - Enable real-time PSU monitoring in Grafana

19. **Create unified health check utility**
    - Script to test all hardware connections
    - NI cDAQ (analog + relay), Pico TC-08, (PSU when available)
    - Report status, channel counts, firmware versions
    - Save diagnostic log

20. ✅ **Update devices.yaml for Gen3 hardware**
    - Remove MK1 devices (Waveshare modules, BGAs, 10 PSUs)
    - Add NI cDAQ configuration:
      - IP address, module slots, channel mappings
      - Analog input sensor definitions (4-20mA scaling)
      - Relay naming and grouping
    - Add Pico TC-08 configuration:
      - USB device ID, thermocouple types, channel names
    - Add PSU configuration:
      - COM port, baud rate, slave ID, register map
    - Define system parameters (InfluxDB, Grafana)

21. ✅ **Create Telegraf configuration for Gen3**
    - Update `config/telegraf.conf`
    - HTTP input for NI analog bridge (port 8881)
    - HTTP input for Pico TC-08 bridge (port 8882)
    - HTTP input for PSU bridge (port 8883, optional)
    - Remove old Modbus TCP inputs (MK1 devices)
    - Configure output to InfluxDB

22. ✅ **Test individual hardware bridges**
    - Start NI analog bridge, verify `/metrics` returns data
    - Start Pico TC-08 bridge, verify `/metrics` returns data
    - Start PSU bridge (if implemented), verify `/metrics` returns data
    - Check InfluxDB line protocol format

23. ✅ **Test end-to-end monitoring pipeline**
    - Start Docker stack: `docker compose up -d`
    - Start all hardware bridges
    - Verify data flowing: Telegraf → InfluxDB
    - Query InfluxDB for measurements: `ni_analog`, `tc08`, `psu`
    - Check data rate and completeness

24. ✅ **Create systemd equivalents for Windows**
    - Option A: Use Windows Task Scheduler for auto-start
    - Option B: Use NSSM (Non-Sucking Service Manager) to run Python bridges as services
    - Configure bridges to auto-restart on failure
    - Document service management commands

25. ✅ **Hardware integration testing**
    - Run all bridges simultaneously
    - Monitor system resource usage (CPU, memory, network)
    - Stress test: rapid relay toggling, high-frequency analog reads
    - Verify no data loss or crashes

---

### Phase 3: Control GUI Implementation (26-40)

26. ✅ **Create GUI project structure**
    - Adapted MK1_AWE/gui/ in place for Gen3
    - Updated imports for Gen3 hardware clients
    - Removed MK1-specific dependencies

27. ✅ **Implement config loader for Gen3**
    - Existing config_loader.py works with Gen3 devices.yaml
    - Helper functions compatible with new structure
    - Validation on load functional

28. ✅ **Implement NI relay client for GUI**
    - Created `ni_relay_client.py` with NI-DAQmx integration
    - Thread-safe operations
    - 16 relays supported

29. ✅ **Implement PSU client for GUI**
    - Created `psu_rtu_client.py` (HTTP-based, no COM conflicts)
    - Safety limits: 100-900V, 1-100A
    - Thread-safe HTTP operations

30. ✅ **Create main window layout**
    - Dark theme maintained
    - Single-view design
    - Sections: Hardware Status, BGA Purge, PSU Settings, Relay Controls

31. ✅ **Implement hardware status indicators**
    - Status for: AIM, RLM, TCM, BGA01/02/03, PSU
    - Color-coded: Green=Online, Red=Offline
    - Background worker with 5s refresh

32. ✅ **Implement relay panel widget**
    - 16 relay buttons (RL01-RL16) in single group
    - Toggle buttons: Gray=OFF, Green=ON
    - NI-DAQmx based control
    - Disabled when cDAQ offline

33. ✅ **Implement PSU panel widget**
    - Input fields: Voltage (100-900V), Current (1-100A)
    - Buttons: Enter, Stop, Ramp, Profile all functional
    - Mode-aware for gen3
    - Disabled when PSU offline

34. ✅ **Implement profile execution for single PSU**
    - CSV format supported
    - Fixed voltage, variable current from profile
    - Non-blocking execution with progress bar
    - Interruptible via Stop button

35. ✅ **Implement ramp functionality**
    - Linear ramp from 0 to user input current
    - Fixed voltage from user input
    - 20 steps × 6s configurable in devices.yaml
    - Visual feedback (progress bar, countdown timer)

36. ✅ **Add safety interlocks**
    - Hardware-dependent control enabling
    - Safe startup: All relays OFF, PSU disabled
    - Safe shutdown: PSU → 0V/0A/OFF, then relays OFF
    - Voltage/current limits enforced in client

37. ✅ **Add disconnect monitoring**
    - Detects hardware disconnections (all devices)
    - Automatically disables controls
    - Shows non-blocking alert dialog
    - Auto-recovery on reconnection

38. ✅ **Add logging and diagnostics**
    - All control actions logged to console
    - Suppressed library noise (pymodbus, nidaqmx)
    - Clear status messages

39. ✅ **GUI testing with hardware**
    - GUI launches successfully
    - All widgets render correctly
    - Relay toggle operations tested
    - PSU voltage/current control tested
    - Ramp and profile execution tested
    - Safe startup and shutdown tested

40. ✅ **GUI polish and documentation**
    - Desktop shortcut with icon created
    - Error messages clear and styled
    - Consistent dark theme
    - App icon in taskbar

---

### Phase 4: Grafana Dashboards (41-45)

41. ✅ **Start Grafana and configure data source**
    - Access Grafana UI: http://localhost:3000
    - Add InfluxDB v2 data source
    - Configure org, bucket, token
    - Test connection

42. ✅ **Create Gen3 dashboard layout**
    - Design panel structure:
      - Row 1: Analog inputs (16 channels, raw mA)
      - Row 2: Thermocouples (8 channels, °C)
      - Row 3: Relay states (16 channels, binary) - TBD
      - Row 4: PSU (V, I, P, status) - ON HOLD

43. ✅ **Create Flux queries for analog inputs**
    - Query `ni_analog` measurement
    - Apply engineering unit conversions
    - Graphing: Time series with thresholds/annotations
    - Save example queries to `Gen3_AWE/grafana/queries.flux`

44. ✅ **Create Flux queries for thermocouples**
    - Query `tc08` measurement
    - Graph all 8 channels with color coding
    - Add temperature thresholds (high/low alarms)

45. ✅ **Create Flux queries for PSU** (Relays TBD)
    - PSU: Voltage (Actual vs Set) panel created
    - PSU: Current (Actual vs Set) panel created
    - Relays: State timeline - TBD (write-only control for now)
    - Annotations: TBD for future

---

### Phase 3B: BGA Integration (56-65)

56. ✅ **Test BGA RS422/USB connectivity**
    - Connect 3 BGAs via RS422/USB adapters
    - Identify COM ports: BGA01=COM8, BGA02=COM3 (BGA03 pending)
    - Test scripts verified (ws_rs422_bga.py)
    - Updated devices.yaml with COM ports

57. ✅ **Adapt BGA HTTP bridges for RS422/USB**
    - Modified `BGA244_http_1.py` for COM8, 9600 baud (BGA01)
    - Modified `BGA244_http_2.py` for COM3, 9600 baud (BGA02)
    - Kept HTTP server architecture and command queue
    - BGA03 bridge pending (COM port TBD)

58. ✅ **Test BGA bridges individually**
    - Start each bridge manually
    - Verify `/metrics` returns BGA data (purity, gases, temp, pressure)
    - Check InfluxDB line protocol format
    - Verified ~2Hz sampling rate (0.5s polling)

59. **Enable BGA inputs in Telegraf**
    - Uncomment BGA01/02 HTTP inputs in telegraf.conf
    - Use `host.docker.internal:8888/8889`
    - Restart Telegraf container
    - Verify BGA data flowing to InfluxDB

60. ✅ **Setup BGA bridges as Windows services**
    - Use NSSM to install 3 BGA bridge services
    - Configure auto-start on boot
    - Configure auto-restart on failure
    - All services auto-load config from devices.yaml

61. ✅ **Test BGA control from GUI**
    - BGA01/02/03 show "Online" in hardware status
    - PURGE button toggles RL04/RL06 (purge valves)
    - BGAs initialized to normal gas config on startup
    - Safe state on GUI close working

62. **Create Grafana panels for BGA data**
    - Panel: Gas purity (%) for all 3 BGAs
    - Panel: BGA temperatures
    - Panel: BGA pressures
    - Panel: Gas composition (primary/secondary labels)

63. **Verify BGA disconnect handling**
    - Disconnect one BGA (unplug USB)
    - GUI should show disconnect alert
    - Controls should remain for other BGAs
    - Reconnect and verify auto-recovery

64. **Test BGA purge functionality end-to-end**
    - Start with normal mode (H2 in O2, O2 in H2)
    - Click PURGE button (should switch to N2)
    - Verify all 3 BGAs change secondary gas
    - Release PURGE (should return to normal)
    - Monitor in Grafana

65. **Document BGA operations**
    - Update README with BGA commands
    - Document gas reference (CAS numbers)
    - Add BGA troubleshooting section
    - Document purge procedures

---

### Phase 5: Data Export and Analysis (46-55)

46. ✅ **Update test_config.py for Gen3**
    - Change measurement names: `analog_inputs` → `ni_analog`, `modbus` → `tc08`/`ni_relays`
    - Update field names: AI01-AI16 (16 channels), TC01-TC08 (8 channels), RL01-RL16
    - Add PSU measurement configuration
    - Add BGA01/02/03 support
    - Keep sensor conversion structure

47. ✅ **Update export_csv.py for Gen3**
    - Update measurement queries:
      - `ni_analog` for analog inputs (AI01-AI16, raw_ma field)
      - `tc08` for thermocouples (TC01-TC08, temp_c field)
      - `ni_relays` for relay states (RL01-RL16, integer 1/0)
      - `psu` for PSU data (voltage, current, power, etc.)
      - `bga_metrics` for BGAs (purity, uncertainty, temp, pressure)
    - Export each measurement to separate CSV
    - Keep downsampling and time range from test_config.py
    - Handle Gen3 field structure (tagged vs fields)

48. ✅ **Update plot_data.py for Gen3**
    - Plot analog inputs (AI01-AI16, raw mA)
    - Plot thermocouples (TC01-TC08) + BGA temps
    - Plot PSU (voltage, current, power on 3 subplots with actual vs set)
    - Plot BGA purity (all 3 BGAs)
    - Updated purge/active period shading (BGA N2, PSU current > 1A)
    - Removed MK1-specific plots (cell voltages, converted sensors)

49. ✅ **Test standalone export/plot workflow**
    - Edit test_config.py with real test times
    - Run `python export_csv.py` - verify CSVs created
    - Run `python plot_data.py` - verify plots generated
    - Run `python process_test.py` - verify full pipeline
    - Check output quality and completeness

50. ✅ **Create GUI export dialog widget**
    - New file: `MK1_AWE/gui/widgets/export_dialog.py`
    - Popup with 3 text inputs:
      - Test Name (string)
      - Start Time (YYYY-MM-DD_HH_MM_SS in PT)
      - End Time (YYYY-MM-DD_HH_MM_SS in PT)
    - Validation:
      - Date format check (datetime.strptime)
      - Start < End check
      - Show error popups for invalid inputs
    - Updates test_config.py with new values
    - Signals parent to run export

51. ✅ **Add Save button to GUI**
    - Add "SAVE DATA" button to main_window.py (centered row between status and relays)
    - Button opens export dialog
    - Button enabled always (independent of hardware)
    - Styled purple to stand out

52. ✅ **Integrate export execution in GUI**
    - Export dialog updates test_config.py, then signals main window
    - Main window runs process_test.py as subprocess
    - Status bar shows progress/completion
    - Success/error popups with results

53. ✅ **Test GUI export workflow**
    - Launch GUI
    - Click "Save Data..." button in hardware status
    - Date/time pickers for easy selection
    - CSV files created with labels
    - Plots generated successfully
    - Error handling working (date validation, format checks)

54. **Add export menu/options** (OPTIONAL - Future)
    - Add "Export plots automatically" checkbox
    - Add "Open folder after export" checkbox
    - Add recent test list (quick re-export)
    - Add default time range (last hour, last 30 min)

55. **Document export workflow** (OPTIONAL - Future)
    - Update README with export instructions
    - Document standalone vs GUI export
    - Document file structure (CSVs, plots, config)
    - Document test_config.py configuration options

---

### Phase 6: Documentation and Finalization (66-70)

66. ✅ **Update README.md for Gen3**
    - System overview (Gen3 hardware)
    - Architecture diagram
    - Quick start guide (Windows-specific)
    - Hardware table (NI, Pico, PSU, BGAs)
    - Software stack (Docker on Windows)
    - Control GUI usage
    - Troubleshooting section (Windows-specific issues)

67. ✅ **Update architecture.md for Gen3**
    - High-level system diagram
    - Component responsibilities (bridges, Telegraf, GUI)
    - Data flow (hardware → HTTP → Telegraf → InfluxDB → Grafana)
    - Configuration management (devices.yaml)
    - Safety and state management
    - Windows-specific considerations

68. **Create Windows setup guide**
    - Document: `MK1_AWE/docs/windows_setup.md`
    - Step-by-step: Docker, Python, NI drivers, Pico drivers
    - Screenshots for key steps
    - Troubleshooting common Windows issues

69. **Create hardware validation guide**
    - Document: `MK1_AWE/docs/hardware_validation.md`
    - Test procedures for each device
    - Expected outputs and pass/fail criteria
    - Diagnostic commands

70. **Final system integration test**
    - Full startup sequence: Docker → Bridges → GUI
    - Run 30-minute test with all hardware
    - Monitor for errors, crashes, data gaps
    - Document any issues and resolutions

---

## ✅ Completed (from MK1 - Reference Only)

### Reusable Components
- Docker compose stack (InfluxDB, Telegraf, Grafana)
- PySide6 GUI framework (dark theme, modern widgets)
- Profile execution engine (CSV-based current profiles)
- CSV export and plotting tools (adaptable to new measurements)
- Configuration loader (devices.yaml parser)
- Safe state management patterns

### Not Applicable for Gen3
- BGA control (no gas analyzers in Gen3)
- Multi-PSU parallel control (single PSU in Gen3)
- Modbus TCP networking (Gen3 uses NI-DAQmx, Pico SDK, Modbus RTU)
- SSH/X11 forwarding (Windows local GUI, no remote access needed initially)

---

## 📋 Future Enhancements

### Advanced Features
- Remote desktop access (VNC, RDP, or TeamViewer)
- Email/SMS alerts on critical events (overtemp, overpressure, PSU fault)
- Automated test sequencing (multiple profiles in series)
- Data-driven safety limits (adaptive thresholds based on historical data)

### GUI Improvements
- Plotting within GUI (live charts using pyqtgraph or matplotlib)
- Relay bulk operations (All ON/All OFF)
- Custom relay naming via GUI
- User profiles with saved presets

### System Integration
- Auto-generate telegraf.conf from devices.yaml
- Log all control actions to InfluxDB (audit trail)
- GUI-triggered data snapshots (quick export button)

### Testing & Validation
- Unit tests for clients (mocked hardware)
- Integration tests with hardware simulator
- Automated acceptance tests
- CI/CD pipeline for code validation

---

## 🔍 Key Differences: MK1 → Gen3

| Aspect | MK1 | Gen3 |
|--------|-----|------|
| **Platform** | Ubuntu 22.04 | Windows 10/11 |
| **Analog Input** | Waveshare AIM (Modbus TCP) | NI-9253 (NI-DAQmx) |
| **Thermocouples** | Waveshare TCM (Modbus TCP) | Pico TC-08 (USB) |
| **Relays** | Waveshare RLM (Modbus TCP) | NI-9485 (NI-DAQmx) |
| **PSU** | 10x Modbus TCP | 1x Modbus RTU (USB) |
| **Connectivity** | Ethernet (PoE) | Ethernet + USB |
| **Display** | SSH/X11 forwarding | Local Windows GUI |
| **Bridge Services** | systemd | Task Scheduler or NSSM |

---

## 📝 Notes
- Windows paths use backslashes: `Gen3_AWE\config\devices.yaml`
- Virtual environment activation: `venv\Scripts\activate` (not `source venv/bin/activate`)
- Docker Desktop requires Hyper-V or WSL2 (Windows 10 Pro or Windows 11)
- NI-DAQmx drivers are ~2 GB download, ~5 GB installed
- Pico TC-08 has 1Hz max sample rate (hardware limitation)
- USB device COM port assignment may change; use device serial number for stability
