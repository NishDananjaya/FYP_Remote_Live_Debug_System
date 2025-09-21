import sys
import json
import time
import threading
import csv
from collections import deque
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QTextEdit, QComboBox,
                             QGroupBox, QSplitter, QStatusBar, QMessageBox, QDialog,
                             QDialogButtonBox, QSpinBox, QGridLayout, QTabWidget,
                             QFileDialog, QCheckBox, QProgressBar, QMenuBar)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
import pyqtgraph as pg
import numpy as np
import os

# Import the modified server class
from server import WebSocketServer
from logger_config import get_module_logger
from ota_handler import OTAHandler, OTAStatus

# Get logger for this module
logger = get_module_logger("GUI")

class DataExporter:
    """Handle data export functionality"""
    @staticmethod
    def export_to_csv(data_points, filename=None):
        """Export monitoring data to CSV file"""
        if not filename:
            filename, _ = QFileDialog.getSaveFileName(
                None, "Save Data", "", "CSV Files (*.csv);;All Files (*)"
            )
        
        if filename and data_points:
            try:
                with open(filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Parameter', 'Value', 'Timestamp', 'Time String'])
                    
                    for param, points in data_points.items():
                        for value, timestamp in points:
                            time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                            writer.writerow([param, value, timestamp, time_str])
                
                logger.info(f"Data exported to {filename}")
                return True
            except Exception as e:
                logger.error(f"Failed to export data: {e}")
                return False
        return False

class SettingsManager:
    """Manage application settings"""
    def __init__(self, settings_file="settings.json"):
        self.settings_file = Path(settings_file)
        self.settings = self.load_settings()
    
    def load_settings(self):
        """Load settings from file"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
        return self.get_default_settings()
    
    def save_settings(self, settings):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
            logger.info("Settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    def get_default_settings(self):
        """Get default settings"""
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 8000
            },
            "monitoring": {
                "update_interval": 500,
                "max_data_points": 1000
            },
            "ui": {
                "theme": "Fusion",
                "log_max_lines": 1000
            },
            "alerts": {}
        }

class AlertManager(QDialog):
    """Manage alert configurations"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.alerts = {}
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Alert Configuration")
        self.setModal(True)
        layout = QVBoxLayout(self)
        
        # Create alert configuration grid
        grid = QGridLayout()
        
        # Headers
        grid.addWidget(QLabel("Parameter"), 0, 0)
        grid.addWidget(QLabel("Min Value"), 0, 1)
        grid.addWidget(QLabel("Max Value"), 0, 2)
        grid.addWidget(QLabel("Enabled"), 0, 3)
        
        # Alert configurations for each parameter
        self.alert_configs = {}
        parameters = ["Voltage", "Current", "Active Ports"]
        
        for i, param in enumerate(parameters, 1):
            grid.addWidget(QLabel(param), i, 0)
            
            min_spin = QSpinBox()
            min_spin.setRange(-1000, 1000)
            min_spin.setValue(0)
            grid.addWidget(min_spin, i, 1)
            
            max_spin = QSpinBox()
            max_spin.setRange(-1000, 1000)
            max_spin.setValue(100)
            grid.addWidget(max_spin, i, 2)
            
            enabled_check = QCheckBox()
            grid.addWidget(enabled_check, i, 3)
            
            self.alert_configs[param] = {
                'min': min_spin,
                'max': max_spin,
                'enabled': enabled_check
            }
        
        layout.addLayout(grid)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_alerts(self):
        """Get current alert configuration"""
        alerts = {}
        for param, config in self.alert_configs.items():
            if config['enabled'].isChecked():
                alerts[param] = {
                    'min': config['min'].value(),
                    'max': config['max'].value()
                }
        return alerts

class RealTimePlotWidget(pg.PlotWidget):
    def __init__(self, parent=None, title="Real-time Data", y_label="Value"):
        super().__init__(parent=parent)
        self.setTitle(title, color="#333333", size="12pt")
        self.setLabel('left', y_label)
        self.setLabel('bottom', 'Time (s)')
        self.addLegend()
        self.setBackground('w')
        self.showGrid(x=True, y=True)
        
        # Store plot data references
        self.data_curves = {}
        self.data_points = {}  # Store data points by parameter
        self.visible_parameters = set()  # Parameters to show
        
        logger.debug("RealTimePlotWidget initialized")
        
    def set_visible_parameters(self, parameters):
        """Set which parameters should be visible on the plot"""
        self.visible_parameters = set(parameters)
        self.update_plot_visibility()
        logger.debug(f"Visible parameters set to: {parameters}")
        
    def update_plot_visibility(self):
        """Show/hide curves based on visible parameters"""
        for param, curve in self.data_curves.items():
            curve.setVisible(param in self.visible_parameters or not self.visible_parameters)
        
    def update_plot(self, parameter, value, timestamp):
        # Initialize deque for this parameter if it doesn't exist
        if parameter not in self.data_points:
            self.data_points[parameter] = deque(maxlen=1000)  # Store last 1000 data points
            logger.debug(f"Created new data series for parameter: {parameter}")
        
        # Add new data point
        self.data_points[parameter].append((value, timestamp))
        
        # Update the curve for this parameter
        if parameter not in self.data_curves:
            color = pg.intColor(len(self.data_curves) * 30, hues=9, maxValue=200)
            self.data_curves[parameter] = self.plot(
                [], [], 
                name=parameter, 
                pen=pg.mkPen(color=color, width=2),
                symbol='o',
                symbolSize=5,
                symbolBrush=color
            )
            # Set initial visibility
            self.data_curves[parameter].setVisible(
                parameter in self.visible_parameters or not self.visible_parameters
            )
            logger.debug(f"Created new curve for parameter: {parameter}")
        
        # Extract data for this parameter
        times = [point[1] for point in self.data_points[parameter]]
        values = [point[0] for point in self.data_points[parameter]]
        
        # Update the curve
        if times and values:
            self.data_curves[parameter].setData(times, values)
    
    def clear_data(self):
        """Clear all plot data"""
        self.data_points.clear()
        for curve in self.data_curves.values():
            curve.setData([], [])
        logger.debug("Plot data cleared")

class DataMonitorGUI(QMainWindow):
    data_received = pyqtSignal(str, float, float)  # parameter, value, timestamp
    
    def __init__(self):
        super().__init__()
        
        logger.info("Initializing DataMonitorGUI")
        
        # Initialize managers
        self.settings_manager = SettingsManager()
        self.alert_manager = AlertManager(self)
        self.active_alerts = {}
        
        # Create server instance
        self.server = WebSocketServer()
        # Set our method as the data callback
        self.server.data_callback = self.on_data_received
        
        # Store latest parameter values
        self.parameter_values = {
            "Voltage": 0.0,
            "Current": 0.0,
            "Active Ports": 0
        }
        
        self.init_ui()
        self.setup_connections()
        self.apply_settings()
        
        # Start the server in a separate thread
        self.server_thread = threading.Thread(target=self.server.run)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        # Start connection status timer
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.update_connection_status)
        self.connection_timer.start(1000)  # Update every second
        
        logger.info("DataMonitorGUI initialization complete")

        
    def init_ui(self):
        self.setWindowTitle("WebSocket Server Data Monitor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.tuning_tab = QWidget()
        self.monitoring_tab = QWidget()
        self.ota_tab = QWidget()
        
        # Add tabs to tab widget
        self.tab_widget.addTab(self.tuning_tab, "Tuning")
        self.tab_widget.addTab(self.monitoring_tab, "Monitoring")
        self.tab_widget.addTab(self.ota_tab, "OTA Updates")
        
        # Setup each tab
        self.setup_tuning_tab()
        self.setup_monitoring_tab()
        self.setup_ota_tab()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Add connection status label to status bar
        self.connection_label = QLabel("● Disconnected")
        self.connection_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        self.status_bar.addPermanentWidget(self.connection_label)
        
        self.update_status("Server started on port 8000")
        
        # Add widgets to main layout
        main_layout.addWidget(self.tab_widget)
        
        logger.debug("GUI UI initialized")
    
    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        export_action = file_menu.addAction('Export Data')
        export_action.triggered.connect(self.export_data)
        
        save_settings_action = file_menu.addAction('Save Settings')
        save_settings_action.triggered.connect(self.save_current_settings)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)
        
        # View menu
        view_menu = menubar.addMenu('View')
        
        clear_log_action = view_menu.addAction('Clear Log')
        clear_log_action.triggered.connect(lambda: self.log_text.clear())
        
        clear_plot_action = view_menu.addAction('Clear Plot')
        clear_plot_action.triggered.connect(lambda: self.plot_widget.clear_data())
        
        # Tools menu
        tools_menu = menubar.addMenu('Tools')
        
        alerts_action = tools_menu.addAction('Configure Alerts')
        alerts_action.triggered.connect(self.configure_alerts)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        about_action = help_menu.addAction('About')
        about_action.triggered.connect(lambda: QMessageBox.about(
            self, "About", 
            "WebSocket Server Data Monitor\nVersion 1.0\n\nA real-time data monitoring application"
        ))
        
    def setup_tuning_tab(self):
        layout = QVBoxLayout(self.tuning_tab)
        
        # Control panel
        control_group = QGroupBox("Tuning Controls")
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh Parameters")
        self.write_data_btn = QPushButton("Write Data")
        
        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.write_data_btn)
        control_layout.addStretch()
        
        control_group.setLayout(control_layout)
        
        # Write data section
        write_data_group = QGroupBox("Write Data - Enter 4 Bytes")
        write_data_layout = QGridLayout()
        
        # Create spin boxes for each byte
        self.byte_spinboxes = []
        for i in range(4):
            label = QLabel(f"Byte {i+1}:")
            spinbox = QSpinBox()
            spinbox.setRange(0, 255)
            spinbox.setValue(0)
            self.byte_spinboxes.append(spinbox)
            
            write_data_layout.addWidget(label, i, 0)
            write_data_layout.addWidget(spinbox, i, 1)
        
        write_data_group.setLayout(write_data_layout)
        
        # Parameters display area
        params_group = QGroupBox("Parameters")
        params_layout = QVBoxLayout()
        
        # Create a scroll area for parameters (simplified for now)
        self.params_text = QTextEdit()
        self.params_text.setReadOnly(True)
        self.params_text.setPlainText("Parameter 1: Value\nParameter 2: Value\nParameter 3: Value")
        params_layout.addWidget(self.params_text)
        
        params_group.setLayout(params_layout)
        
        # Add widgets to tuning tab layout
        layout.addWidget(control_group)
        layout.addWidget(write_data_group)
        layout.addWidget(params_group)
        
    def setup_monitoring_tab(self):
        layout = QVBoxLayout(self.monitoring_tab)
        
        # Control panel
        control_group = QGroupBox("Monitoring Controls")
        control_layout = QHBoxLayout()
        
        self.start_monitoring_btn = QPushButton("Start Monitoring")
        self.stop_monitoring_btn = QPushButton("Stop Monitoring")
        self.export_btn = QPushButton("Export Data")
        self.configure_alerts_btn = QPushButton("Configure Alerts")
        
        # Parameter selection
        control_layout.addWidget(QLabel("Show Parameter:"))
        self.parameter_combo = QComboBox()
        self.parameter_combo.addItems(["All Parameters", "Voltage", "Current", "Active Ports"])
        self.parameter_combo.currentTextChanged.connect(self.on_parameter_changed)
        control_layout.addWidget(self.parameter_combo)
        
        control_layout.addWidget(self.start_monitoring_btn)
        control_layout.addWidget(self.stop_monitoring_btn)
        control_layout.addWidget(self.export_btn)
        control_layout.addWidget(self.configure_alerts_btn)
        control_layout.addStretch()
        
        control_group.setLayout(control_layout)
        
        # Plot area
        plot_widget = QWidget()
        plot_layout = QHBoxLayout(plot_widget)
        
        self.plot_widget = RealTimePlotWidget(title="Real-time Data Monitoring", y_label="Value")
        plot_layout.addWidget(self.plot_widget)
        
        # Log area
        log_group = QGroupBox("Event Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        # Add widgets to monitoring tab layout
        layout.addWidget(control_group)
        layout.addWidget(self.plot_widget)
        layout.addWidget(log_group)
        
        # Set initial button states
        self.stop_monitoring_btn.setEnabled(False)
    
    def setup_ota_tab(self):
 
        
        # Initialize OTA handler
        self.ota_handler = OTAHandler(self.server)
        self.ota_handler.set_callbacks(
            status_cb=self.on_ota_status_update,
            progress_cb=self.on_ota_progress_update,
            log_cb=self.on_ota_log
        )
        
        layout = QVBoxLayout(self.ota_tab)
        
        # File selection group
        file_group = QGroupBox("Firmware File Selection")
        file_layout = QHBoxLayout()
        
        self.firmware_path_edit = QTextEdit()
        self.firmware_path_edit.setMaximumHeight(30)
        self.firmware_path_edit.setReadOnly(True)
        
        self.browse_firmware_btn = QPushButton("Browse...")
        self.browse_firmware_btn.clicked.connect(self.browse_firmware)
        
        file_layout.addWidget(QLabel("Firmware File:"))
        file_layout.addWidget(self.firmware_path_edit)
        file_layout.addWidget(self.browse_firmware_btn)
        
        file_group.setLayout(file_layout)
        
        # Update controls
        control_group = QGroupBox("Update Controls")
        control_layout = QGridLayout()
        
        # Device selection
        control_layout.addWidget(QLabel("Target Device:"), 0, 0)
        self.device_combo = QComboBox()
        self.refresh_devices_btn = QPushButton("Refresh")
        self.refresh_devices_btn.clicked.connect(self.refresh_device_list)
        control_layout.addWidget(self.device_combo, 0, 1)
        control_layout.addWidget(self.refresh_devices_btn, 0, 2)
        
        # Version info
        control_layout.addWidget(QLabel("Current Version:"), 1, 0)
        self.current_version_label = QLabel("Unknown")
        control_layout.addWidget(self.current_version_label, 1, 1)
        
        control_layout.addWidget(QLabel("New Version:"), 2, 0)
        self.new_version_label = QLabel("N/A")
        control_layout.addWidget(self.new_version_label, 2, 1)
        
        control_layout.addWidget(QLabel("File Size:"), 3, 0)
        self.file_size_label = QLabel("N/A")
        control_layout.addWidget(self.file_size_label, 3, 1)
        
        # Update buttons
        self.verify_firmware_btn = QPushButton("Verify Firmware")
        self.verify_firmware_btn.clicked.connect(self.verify_firmware)
        control_layout.addWidget(self.verify_firmware_btn, 4, 0)
        
        self.start_update_btn = QPushButton("Start Update")
        self.start_update_btn.clicked.connect(self.start_ota_update)
        self.start_update_btn.setEnabled(False)
        control_layout.addWidget(self.start_update_btn, 4, 1)
        
        self.cancel_update_btn = QPushButton("Cancel Update")
        self.cancel_update_btn.clicked.connect(self.cancel_ota_update)
        self.cancel_update_btn.setEnabled(False)
        control_layout.addWidget(self.cancel_update_btn, 4, 2)
        
        control_group.setLayout(control_layout)
        
        # Progress group
        progress_group = QGroupBox("Update Progress")
        progress_layout = QVBoxLayout()
        
        # Status label
        self.ota_status_label = QLabel("Status: Idle")
        self.ota_status_label.setStyleSheet("font-weight: bold;")
        progress_layout.addWidget(self.ota_status_label)
        
        self.update_progress = QProgressBar()
        self.update_progress.setMinimum(0)
        self.update_progress.setMaximum(100)
        
        self.update_status_text = QTextEdit()
        self.update_status_text.setReadOnly(True)
        self.update_status_text.setMaximumHeight(150)
        
        progress_layout.addWidget(self.update_progress)
        progress_layout.addWidget(self.update_status_text)
        
        progress_group.setLayout(progress_layout)
        
        # Add all groups to main layout
        layout.addWidget(file_group)
        layout.addWidget(control_group)
        layout.addWidget(progress_group)
        layout.addStretch()
        
        # Initialize device list
        self.refresh_device_list()

    def refresh_device_list(self):
        """Refresh the list of connected devices"""
        self.device_combo.clear()
        self.device_combo.addItem("All Devices")
        
        devices = self.ota_handler.get_device_info()
        for device in devices:
            self.device_combo.addItem(f"Device {device.device_id}")
        
        self.update_status_text.append(f"Found {len(devices)} connected devices")

    def browse_firmware(self):
        """Browse for firmware file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "", 
            "Binary Files (*.bin);;Hex Files (*.hex);;All Files (*)"
        )
        if filename:
            self.firmware_path_edit.setText(filename)
            self.update_status_text.append(f"Selected: {os.path.basename(filename)}")

    def verify_firmware(self):
        """Verify firmware file using OTA handler"""
        firmware_path = self.firmware_path_edit.toPlainText()
        if not firmware_path:
            QMessageBox.warning(self, "No File", "Please select a firmware file first")
            return
        
        success, firmware_info = self.ota_handler.validate_firmware(firmware_path)
        
        if success:
            self.new_version_label.setText(firmware_info.version)
            self.file_size_label.setText(f"{firmware_info.file_size:,} bytes")
            self.start_update_btn.setEnabled(True)
            QMessageBox.information(self, "Success", 
                f"Firmware validated successfully!\n"
                f"Version: {firmware_info.version}\n"
                f"Size: {firmware_info.file_size:,} bytes\n"
                f"Chunks: {firmware_info.chunks}")
        else:
            QMessageBox.critical(self, "Error", "Firmware validation failed")

    def start_ota_update(self):
        """Start OTA update process"""
        firmware_path = self.firmware_path_edit.toPlainText()
        if not firmware_path:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Update", 
            "Are you sure you want to start the firmware update?\n"
            "This process cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Get selected device(s)
            device_selection = self.device_combo.currentText()
            device_ids = None
            
            if device_selection != "All Devices":
                # Extract device ID from combo text
                device_id = device_selection.replace("Device ", "")
                device_ids = [device_id]
            
            # Start update
            if self.ota_handler.start_update(firmware_path, device_ids):
                self.start_update_btn.setEnabled(False)
                self.cancel_update_btn.setEnabled(True)
                self.verify_firmware_btn.setEnabled(False)
                self.browse_firmware_btn.setEnabled(False)
            else:
                QMessageBox.critical(self, "Error", "Failed to start OTA update")

    def cancel_ota_update(self):
        """Cancel ongoing OTA update"""
        reply = QMessageBox.question(
            self, "Confirm Cancel", 
            "Are you sure you want to cancel the update?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.ota_handler.cancel_update()
            self.cancel_update_btn.setEnabled(False)

    def on_ota_status_update(self, status, message):
        """Handle OTA status updates"""
        from src.ota_handler import OTAStatus
        
        self.ota_status_label.setText(f"Status: {status.value.upper()}")
        
        # Update UI based on status
        if status == OTAStatus.COMPLETED:
            self.ota_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.start_update_btn.setEnabled(True)
            self.cancel_update_btn.setEnabled(False)
            self.verify_firmware_btn.setEnabled(True)
            self.browse_firmware_btn.setEnabled(True)
            QMessageBox.information(self, "Success", "Firmware update completed successfully!")
            
        elif status == OTAStatus.FAILED:
            self.ota_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.start_update_btn.setEnabled(True)
            self.cancel_update_btn.setEnabled(False)
            self.verify_firmware_btn.setEnabled(True)
            self.browse_firmware_btn.setEnabled(True)
            QMessageBox.critical(self, "Error", f"Update failed: {message}")
            
        elif status == OTAStatus.CANCELLED:
            self.ota_status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.start_update_btn.setEnabled(True)
            self.cancel_update_btn.setEnabled(False)
            self.verify_firmware_btn.setEnabled(True)
            self.browse_firmware_btn.setEnabled(True)
            
        else:
            self.ota_status_label.setStyleSheet("color: blue; font-weight: bold;")

    def on_ota_progress_update(self, progress):
        """Handle OTA progress updates"""
        self.update_progress.setValue(progress)

    def on_ota_log(self, message):
        """Handle OTA log messages"""
        timestamp = time.strftime('%H:%M:%S')
        self.update_status_text.append(f"[{timestamp}] {message}")
        
    def setup_connections(self):
        self.data_received.connect(self.plot_widget.update_plot)
        self.data_received.connect(self.log_data)
        
        self.start_monitoring_btn.clicked.connect(self.start_monitoring)
        self.stop_monitoring_btn.clicked.connect(self.stop_monitoring)
        self.write_data_btn.clicked.connect(self.write_data)
        self.refresh_btn.clicked.connect(self.refresh_parameters)
        self.export_btn.clicked.connect(self.export_data)
        self.configure_alerts_btn.clicked.connect(self.configure_alerts)
        
        logger.debug("GUI connections setup complete")
    
    def apply_settings(self):
        """Apply loaded settings"""
        settings = self.settings_manager.settings
        
        # Apply UI theme
        QApplication.setStyle(settings["ui"]["theme"])
        
        # Load saved alerts if any
        if settings.get("alerts"):
            self.active_alerts = settings["alerts"]
        
        logger.info("Settings applied")
    
    def save_current_settings(self):
        """Save current application settings"""
        settings = {
            "server": {
                "host": self.server.host,
                "port": self.server.port
            },
            "monitoring": {
                "update_interval": 500,
                "max_data_points": 1000
            },
            "ui": {
                "theme": QApplication.style().objectName(),
                "log_max_lines": 1000
            },
            "alerts": self.active_alerts
        }
        
        if self.settings_manager.save_settings(settings):
            self.update_status("Settings saved")
            QMessageBox.information(self, "Settings", "Settings saved successfully")
    
    def update_connection_status(self):
        """Update connection status indicator"""
        if hasattr(self.server, 'clients') and self.server.clients:
            client_count = len(self.server.clients)
            self.connection_label.setText(f"● Connected ({client_count} clients)")
            self.connection_label.setStyleSheet("color: green; font-weight: bold; padding: 5px;")
        else:
            self.connection_label.setText("● Disconnected")
            self.connection_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
    
    def configure_alerts(self):
        """Open alert configuration dialog"""
        if self.alert_manager.exec_():
            self.active_alerts = self.alert_manager.get_alerts()
            self.log_text.append(f"Alerts configured: {list(self.active_alerts.keys())}")
            logger.info(f"Alerts configured: {self.active_alerts}")
    
    def check_alerts(self, parameter, value):
        """Check if value triggers any alerts"""
        if parameter in self.active_alerts:
            alert_config = self.active_alerts[parameter]
            if value < alert_config['min'] or value > alert_config['max']:
                alert_msg = f"⚠️ ALERT: {parameter} = {value:.2f} (Range: {alert_config['min']}-{alert_config['max']})"
                self.log_text.append(f"<b style='color: red;'>{alert_msg}</b>")
                self.status_bar.showMessage(alert_msg, 5000)
                QMessageBox.warning(self, "Alert", alert_msg)
                logger.warning(alert_msg)
    
    def export_data(self):
        """Export current plot data to CSV"""
        if hasattr(self.plot_widget, 'data_points') and self.plot_widget.data_points:
            if DataExporter.export_to_csv(self.plot_widget.data_points):
                self.update_status("Data exported successfully")
                self.log_text.append("Data exported to CSV file")
            else:
                self.update_status("Failed to export data")
        else:
            QMessageBox.warning(self, "No Data", "No data available to export")
    
    def browse_firmware(self):
        """Browse for firmware file"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "", 
            "Binary Files (*.bin);;Hex Files (*.hex);;All Files (*)"
        )
        if filename:
            self.firmware_path_edit.setText(filename)
            self.update_status_text.append(f"Selected firmware: {filename}")
            # Extract version from filename if possible
            import os
            base_name = os.path.basename(filename)
            self.new_version_label.setText(base_name)
    
    def verify_firmware(self):
        """Verify firmware file before update"""
        firmware_path = self.firmware_path_edit.toPlainText()
        if not firmware_path:
            QMessageBox.warning(self, "No File", "Please select a firmware file first")
            return
        
        try:
            import os
            if os.path.exists(firmware_path):
                file_size = os.path.getsize(firmware_path)
                self.update_status_text.append(f"Firmware verified: {file_size} bytes")
                self.start_update_btn.setEnabled(True)
                QMessageBox.information(self, "Verification", "Firmware file verified successfully")
            else:
                QMessageBox.critical(self, "Error", "Firmware file not found")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Verification failed: {e}")
    
    def start_ota_update(self):
        """Start OTA update process"""
        firmware_path = self.firmware_path_edit.toPlainText()
        if not firmware_path:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Update", 
            "Are you sure you want to start the firmware update?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.update_status_text.append("Starting OTA update...")
            self.start_update_btn.setEnabled(False)
            
            # Simulate update progress (replace with actual implementation)
            self.simulate_ota_update()
    
    def simulate_ota_update(self):
        """Simulate OTA update progress"""
        self.ota_timer = QTimer()
        self.ota_progress = 0
        
        def update_progress():
            self.ota_progress += 5
            self.update_progress.setValue(self.ota_progress)
            self.update_status_text.append(f"Updating... {self.ota_progress}%")
            
            if self.ota_progress >= 100:
                self.ota_timer.stop()
                self.update_status_text.append("Update complete!")
                QMessageBox.information(self, "Success", "Firmware update completed successfully")
                self.start_update_btn.setEnabled(True)
                self.update_progress.setValue(0)
        
        self.ota_timer.timeout.connect(update_progress)
        self.ota_timer.start(500)  # Update every 500ms
        
    def refresh_parameters(self):
        """Refresh parameter values by displaying the latest received values"""
        logger.debug("Refreshing parameter display")
        
        # Update the parameters display with the latest values
        params_text = ""
        for param, value in self.parameter_values.items():
            if param == "Active Ports":
                params_text += f"{param}: {int(value)}\n"
            else:
                params_text += f"{param}: {value:.2f}\n"
        
        self.params_text.setPlainText(params_text)
        
        # Also log the refresh action in the monitoring tab
        self.log_text.append("Parameters refreshed - Displaying latest values")
        
    def on_parameter_changed(self, parameter):
        """Handle parameter selection change"""
        logger.debug(f"Parameter selection changed to: {parameter}")
        
        if parameter == "All Parameters":
            self.plot_widget.set_visible_parameters([])  # Show all
        else:
            self.plot_widget.set_visible_parameters([parameter])

    def on_data_received(self, parameter, value, timestamp):
        # This method will be called by the server when data is received
        logger.debug(f"Data received in GUI - Parameter: {parameter}, Value: {value}, Timestamp: {timestamp}")
        
        # Store the parameter value
        if parameter in self.parameter_values:
            self.parameter_values[parameter] = value
        
        # Emit the signal for plotting and logging
        self.data_received.emit(parameter, value, timestamp)
        
    def log_data(self, parameter, value, timestamp):
        time_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
        log_msg = f"{time_str} - {parameter}: {value:.2f}"
        self.log_text.append(log_msg)
        
        # Check alerts
        self.check_alerts(parameter, value)
        
        # Keep log to a reasonable size
        if self.log_text.document().blockCount() > 1000:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
            
    def update_status(self, message):
        self.status_bar.showMessage(message)
        
    def start_monitoring(self):
        logger.info("GUI requested to start monitoring")
        self.server.start_monitoring()
        self.start_monitoring_btn.setEnabled(False)
        self.stop_monitoring_btn.setEnabled(True)
        self.update_status("Monitoring started")
        self.log_text.append("Monitoring started")
        
    def stop_monitoring(self):
        logger.info("GUI requested to stop monitoring")
        self.server.stop_monitoring()
        self.start_monitoring_btn.setEnabled(True)
        self.stop_monitoring_btn.setEnabled(False)
        self.update_status("Monitoring stopped")
        self.log_text.append("Monitoring stopped")
        
    def write_data(self):
        """Send DOWNLOAD command with the specified bytes"""
        logger.info("GUI requested to write data")
        
        try:
            # Get the bytes from spinboxes
            data_bytes = [spinbox.value() for spinbox in self.byte_spinboxes]
            logger.debug(f"Data bytes from GUI: {data_bytes}")
            
            # Use server's write_data_gui method (which handles the complete sequence)
            success = self.server.write_data_gui(data_bytes)
            
            if success:
                self.log_text.append(f"Write operation completed with bytes: {data_bytes}")
                self.update_status(f"Data written: {data_bytes}")
                logger.info(f"Write operation successful: {data_bytes}")
            else:
                self.log_text.append("Error: Failed to complete write operation")
                logger.error("Write operation failed")
                
        except Exception as e:
            error_msg = f"Error sending write command: {e}"
            self.log_text.append(error_msg)
            logger.error(error_msg)
            logger.exception("Full exception details:")

    def closeEvent(self, event):
        # Clean up when closing the application
        logger.info("Application closing, performing cleanup")
        
        # Save settings before closing
        self.save_current_settings()
        
        self.server.stop_monitoring()
        if hasattr(self.server, 'server'):
            self.server.server.shutdown()
            
        logger.info("Application cleanup complete")
        event.accept()

def main():
    # Import logger config to initialize logging
    from src.logger_config import logger
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern style
    
    logger.info("Starting GUI application")
    
    gui = DataMonitorGUI()
    gui.show()
    
    logger.info("GUI application started successfully")
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()