import sys
import json
import time
import threading
from collections import deque
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QTextEdit, QComboBox,
                             QGroupBox, QSplitter, QStatusBar, QMessageBox, QDialog,
                             QDialogButtonBox, QSpinBox, QGridLayout, QTabWidget)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
import pyqtgraph as pg
import numpy as np

# Import the modified server class
from src.server import WebSocketServer
from src.logger_config import get_module_logger

# Get logger for this module
logger = get_module_logger("GUI")

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

class DataMonitorGUI(QMainWindow):
    data_received = pyqtSignal(str, float, float)  # parameter, value, timestamp
    
    def __init__(self):
        super().__init__()
        
        logger.info("Initializing DataMonitorGUI")
        
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
        
        # Start the server in a separate thread
        self.server_thread = threading.Thread(target=self.server.run)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        logger.info("DataMonitorGUI initialization complete")

        
    def init_ui(self):
        self.setWindowTitle("WebSocket Server Data Monitor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
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
        self.update_status("Server started on port 8000")
        
        # Add widgets to main layout
        main_layout.addWidget(self.tab_widget)
        
        logger.debug("GUI UI initialized")
        
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
        
        # Parameter selection
        control_layout.addWidget(QLabel("Show Parameter:"))
        self.parameter_combo = QComboBox()
        self.parameter_combo.addItems(["All Parameters", "Voltage", "Current", "Active Ports"])
        self.parameter_combo.currentTextChanged.connect(self.on_parameter_changed)
        control_layout.addWidget(self.parameter_combo)
        
        control_layout.addWidget(self.start_monitoring_btn)
        control_layout.addWidget(self.stop_monitoring_btn)
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
        layout = QVBoxLayout(self.ota_tab)
        
        # Placeholder for OTA updates tab
        label = QLabel("OTA Updates functionality will be implemented here")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
    def setup_connections(self):
        self.data_received.connect(self.plot_widget.update_plot)
        self.data_received.connect(self.log_data)
        
        self.start_monitoring_btn.clicked.connect(self.start_monitoring)
        self.stop_monitoring_btn.clicked.connect(self.stop_monitoring)
        self.write_data_btn.clicked.connect(self.write_data)
        self.refresh_btn.clicked.connect(self.refresh_parameters)
        
        logger.debug("GUI connections setup complete")
        
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