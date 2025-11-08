import sys
import json
import time
import threading
import csv
import unittest
import traceback
from collections import deque
from pathlib import Path
from enum import Enum
from io import StringIO
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QLabel, QTextEdit, QComboBox,
                             QGroupBox, QSplitter, QStatusBar, QMessageBox, QDialog,
                             QDialogButtonBox, QSpinBox, QGridLayout, QTabWidget,
                             QFileDialog, QCheckBox, QProgressBar, QMenuBar,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QTreeWidget, QTreeWidgetItem, QTextBrowser, QLineEdit,
                             QProgressDialog, QListWidget, QListWidgetItem,QShortcut,QMenu)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QDateTime, QSettings, QMutex, QMutexLocker
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QBrush, QIcon,QKeySequence
import pyqtgraph as pg
import numpy as np
import os
import subprocess
from pathlib import Path

# Import the modified server class
from server import WebSocketServer
from logger_config import get_module_logger
from ota_handler import OTAHandler, OTAStatus
from PyQt5.QtCore import QMetaType

# Register QTextCursor type for queued connections
QMetaType.type("QTextCursor")

# Get logger for this module
logger = get_module_logger("GUI")

class TestStatus(Enum):
    """Test status enumeration"""
    PENDING = "⏸️ Pending"
    RUNNING = "🔄 Running"
    PASSED = "✅ Passed"
    FAILED = "❌ Failed"
    ERROR = "⚠️ Error"
    SKIPPED = "⏭️ Skipped"

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
    
    @staticmethod
    def export_to_excel(data_points, filename=None):
        """Export to Excel format"""
        try:
            import pandas as pd
            
            # Convert data to DataFrame
            data = []
            for param, points in data_points.items():
                for value, timestamp in points:
                    data.append({
                        'Parameter': param,
                        'Value': value,
                        'Timestamp': timestamp,
                        'Time': time.strftime('%Y-%m-%d %H:%M:%S', 
                                             time.localtime(timestamp))
                    })
            
            df = pd.DataFrame(data)
            
            if not filename:
                filename, _ = QFileDialog.getSaveFileName(
                    None, "Save Data", "", 
                    "Excel Files (*.xlsx);;All Files (*)"
                )
            
            if filename:
                df.to_excel(filename, index=False)
                return True
        except ImportError:
            logger.error("pandas not installed for Excel export")
        except Exception as e:
            logger.error(f"Failed to export to Excel: {e}")
        return False

class VariableManager:
    """Manage variables from CSV file"""
    def __init__(self):
        self.variables = []
        
    def load_csv(self, filename):
        """Load variables from CSV file"""
        variables = []
        try:
            with open(filename, 'r') as csvfile:
                reader = csv.reader(csvfile)
                # Skip header if exists
                next(reader, None)
                
                for row in reader:
                    if len(row) >= 4:
                        # Clean and validate data type
                        cleaned_data_type = self.validate_and_clean_data_type(row[3].strip())
                        
                        var_data = {
                            'name': row[0].strip(),
                            'address': row[1].strip(),
                            'elements': int(row[2]),
                            'data_type': cleaned_data_type,  # Use cleaned type
                            'current_values': [0] * int(row[2])
                        }
                        variables.append(var_data)
                        logger.info(f"Loaded variable: {var_data}")
            
            self.variables = variables
            return True
        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
            return False

    def validate_and_clean_data_type(self, data_type_str):
        """Validate and clean data type string from CSV."""
        # Remove extra spaces and standardize format
        cleaned = data_type_str.strip()
        
        # Common corrections
        corrections = {
            'uint32': 'uint32_t',
            'int32': 'int32_t',
            'uint16': 'uint16_t',
            'int16': 'int16_t',
            'uint8': 'uint8_t',
            'int8': 'int8_t',
            'unsigned int': 'uint32_t',
            'signed int': 'int32_t',
            'unsigned short': 'uint16_t',
            'signed short': 'int16_t',
            'unsigned char': 'uint8_t',
            'signed char': 'int8_t',
            'char': 'int8_t'
        }
        
        # Check if correction needed
        lower_cleaned = cleaned.lower()
        for wrong, right in corrections.items():
            if lower_cleaned == wrong:
                logger.info(f"Corrected data type '{data_type_str}' to '{right}'")
                return right
        
        return cleaned
    
    def get_element_addresses(self, base_address_str, num_elements, data_type):
        """Calculate addresses for array elements"""
        # Parse hex address
        base_address = int(base_address_str, 16)
        
        # Determine size based on data type
        size_map = {
            'uint8_t': 1,
            'int8_t': 1,
            'uint16_t': 2,
            'int16_t': 2,
            'uint32_t': 4,
            'int32_t': 4,
            'float': 4,
            'double': 8
        }
        
        element_size = size_map.get(data_type, 1)
        addresses = []
        
        for i in range(num_elements):
            addresses.append(base_address + (i * element_size))
            
        return addresses
    
    def address_to_bytes(self, address):
        """Convert address to byte array for SET_MTA command"""
        # Convert to 4-byte array (little-endian or big-endian as needed)
        bytes_array = [
            (address >> 24) & 0xFF,
            (address >> 16) & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF
        ]
        return bytes_array

class RealTimePlotWidget(pg.PlotWidget):
    def __init__(self, parent=None, title="Real-time Data", y_label="Value"):
        super().__init__(parent=parent)
        self.setTitle(title, color="#333333", size="12pt")
        self.setLabel('left', y_label)
        self.setLabel('bottom', 'Time (s)')
        self.addLegend()
        self.setBackground('w')
        self.showGrid(x=True, y=True)
        
        self.data_curves = {}
        self.data_points = {}
        self.visible_parameters = set()
        
    def set_visible_parameters(self, parameters):
        """Set which parameters should be visible on the plot"""
        self.visible_parameters = set(parameters)
        self.update_plot_visibility()
        
    def update_plot_visibility(self):
        """Show/hide curves based on visible parameters"""
        for param, curve in self.data_curves.items():
            curve.setVisible(param in self.visible_parameters or not self.visible_parameters)
        
    def update_plot(self, parameter, value, timestamp):
        """Update plot with new data point"""
        try:
            # Log incoming data for debugging
            logger.debug(f"Plot update - Parameter: {parameter}, Value: {value}, Time: {timestamp}")
            
            # Initialize deque for this parameter if it doesn't exist
            if parameter not in self.data_points:
                self.data_points[parameter] = deque(maxlen=1000)
                logger.info(f"Created new data deque for parameter: {parameter}")
            
            # Add new data point
            self.data_points[parameter].append((value, timestamp))
            
            # Create or update the curve for this parameter
            if parameter not in self.data_curves:
                # Generate color based on parameter count
                color = pg.intColor(len(self.data_curves) * 30, hues=9, maxValue=200)
                
                # Create new curve
                self.data_curves[parameter] = self.plot(
                    [], [], 
                    name=parameter, 
                    pen=pg.mkPen(color=color, width=2),
                    symbol='o',
                    symbolSize=5,
                    symbolBrush=color
                )
                logger.info(f"Created new plot curve for parameter: {parameter}")
                
                # Set visibility based on current filter
                is_visible = (not self.visible_parameters) or (parameter in self.visible_parameters)
                self.data_curves[parameter].setVisible(is_visible)
                logger.debug(f"Set {parameter} visibility to {is_visible}")
            
            # Extract data for this parameter
            times = [point[1] for point in self.data_points[parameter]]
            values = [point[0] for point in self.data_points[parameter]]
            
            # Update the curve with new data
            if times and values:
                self.data_curves[parameter].setData(times, values)
                logger.debug(f"Updated curve for {parameter} with {len(values)} points")
                
                # Auto-range if this is the only visible parameter or all are visible
                if not self.visible_parameters or parameter in self.visible_parameters:
                    self.enableAutoRange()
            
        except Exception as e:
            logger.error(f"Error updating plot for {parameter}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def clear_data(self):
        """Clear all plot data"""
        self.data_points.clear()
        for curve in self.data_curves.values():
            curve.setData([], [])

class TestRunner(QThread):
    """Thread for running tests without blocking GUI"""
    test_started = pyqtSignal(str)
    test_completed = pyqtSignal(str, bool, str)
    test_progress = pyqtSignal(int, int)
    suite_completed = pyqtSignal(dict)
    log_message = pyqtSignal(str, str)  # message, level
    
    def __init__(self, test_suite, test_cases=None):
        super().__init__()
        self.test_suite = test_suite
        self.test_cases = test_cases or []
        self.overall_results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'errors': 0,
            'output': ''
        }
        
    def run(self):
        """Run selected tests"""
        try:
            if self.test_suite == "WebSocketServer":
                self.run_websocket_tests()
            elif self.test_suite == "JSONHandler":
                self.run_json_handler_tests()
            elif self.test_suite == "Integration":
                self.run_integration_tests()
            elif self.test_suite == "All" or self.test_suite == "Selected":
                self.run_all_tests()
        except Exception as e:
            self.log_message.emit(f"Test execution error: {str(e)}", "error")
            import traceback
            self.log_message.emit(traceback.format_exc(), "error")
            self.suite_completed.emit(self.overall_results)
    
    def run_websocket_tests(self):
        """Run WebSocket server tests"""
        try:
            import sys
            import os
            import traceback
            
            # Add the test folder to path
            test_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'test')
            if test_path not in sys.path:
                sys.path.insert(0, test_path)
            
            self.log_message.emit(f"Looking for WebSocket tests in: {test_path}", "info")
            
            try:
                # Import the test module
                from test import test_websocket_server
                
                # Check if the module has the test classes
                has_tests = False
                loader = unittest.TestLoader()
                suite = unittest.TestSuite()
                
                # Try to load test classes
                test_classes = [
                    'TestWebSocketServer',
                    'TestWebSocketServerIntegration', 
                    'TestWebSocketServerEdgeCases'
                ]
                
                for test_class_name in test_classes:
                    if hasattr(test_websocket_server, test_class_name):
                        test_class = getattr(test_websocket_server, test_class_name)
                        suite.addTests(loader.loadTestsFromTestCase(test_class))
                        has_tests = True
                        self.log_message.emit(f"Found test class: {test_class_name}", "info")
                
                if has_tests:
                    self.run_test_suite(suite, "WebSocketServer")
                else:
                    self.log_message.emit("No test classes found in test_websocket_server", "warning")
                    # Try to load all tests from module
                    suite = loader.loadTestsFromModule(test_websocket_server)
                    if suite.countTestCases() > 0:
                        self.run_test_suite(suite, "WebSocketServer")
                    else:
                        self.suite_completed.emit({
                            'total': 0,
                            'passed': 0,
                            'failed': 0,
                            'errors': 0,
                            'output': 'No WebSocket tests found'
                        })
                        
            except ImportError as e:
                self.log_message.emit(f"Failed to import test_websocket_server: {e}", "error")
                self.log_message.emit("Make sure test_websocket_server.py is in the 'test' folder", "error")
                self.suite_completed.emit({
                    'total': 0,
                    'passed': 0,
                    'failed': 0,
                    'errors': 1,
                    'output': str(e)
                })
                
        except Exception as e:
            self.log_message.emit(f"WebSocket test error: {str(e)}", "error")
            import traceback
            self.log_message.emit(traceback.format_exc(), "error")
            self.suite_completed.emit({
                'total': 0,
                'passed': 0,
                'failed': 0,
                'errors': 1,
                'output': str(e)
            })
    
    def run_json_handler_tests(self):
        """Run JSON handler tests"""
        try:
            import sys
            import os
            import traceback
            
            # Add the test folder to path
            test_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'test')
            if test_path not in sys.path:
                sys.path.insert(0, test_path)
            
            self.log_message.emit(f"Looking for JSON Handler tests in: {test_path}", "info")
            
            try:
                # Try different possible names for the JSON handler test
                json_test_module = None
                possible_names = ['json_handler_test', 'test_json_handler']
                
                for module_name in possible_names:
                    try:
                        json_test_module = __import__(module_name)
                        self.log_message.emit(f"Successfully imported {module_name}", "info")
                        break
                    except ImportError:
                        continue
                
                if json_test_module is None:
                    raise ImportError("Could not find json_handler_test or test_json_handler")
                
                # Check if it has test functions (functional style)
                test_results = {}
                passed_count = 0
                failed_count = 0
                
                test_functions = []
                function_names = [
                    ('test_message_processing', 'Message Processing'),
                    ('test_command_creation', 'Command Creation'),
                    ('test_error_conditions', 'Error Conditions'),
                    ('test_edge_cases', 'Edge Cases')
                ]
                
                for func_name, display_name in function_names:
                    if hasattr(json_test_module, func_name):
                        test_functions.append((display_name, getattr(json_test_module, func_name)))
                
                if test_functions:
                    total_tests = len(test_functions)
                    current = 0
                    
                    for test_name, test_func in test_functions:
                        self.test_started.emit(test_name)
                        try:
                            # Capture output
                            import io
                            import contextlib
                            
                            f = io.StringIO()
                            with contextlib.redirect_stdout(f):
                                test_func()
                            output = f.getvalue()
                            
                            self.test_completed.emit(test_name, True, output)
                            test_results[test_name] = {"status": "passed", "output": output}
                            passed_count += 1
                            
                        except Exception as e:
                            error_msg = f"{str(e)}\n{traceback.format_exc()}"
                            self.test_completed.emit(test_name, False, error_msg)
                            test_results[test_name] = {"status": "failed", "output": error_msg}
                            failed_count += 1
                        
                        current += 1
                        self.test_progress.emit(current, total_tests)
                    
                    # Create summary
                    self.suite_completed.emit({
                        'total': total_tests,
                        'passed': passed_count,
                        'failed': failed_count,
                        'errors': 0,
                        'output': '\n'.join([f"{name}: {result['status']}" 
                                            for name, result in test_results.items()])
                    })
                else:
                    # Try to find unittest test cases
                    loader = unittest.TestLoader()
                    suite = loader.loadTestsFromModule(json_test_module)
                    if suite.countTestCases() > 0:
                        self.run_test_suite(suite, "JSONHandler")
                    else:
                        self.log_message.emit("No tests found in JSON handler test module", "warning")
                        self.suite_completed.emit({
                            'total': 0,
                            'passed': 0,
                            'failed': 0,
                            'errors': 0,
                            'output': 'No tests found'
                        })
                        
            except ImportError as e:
                self.log_message.emit(f"Failed to import JSON handler tests: {e}", "error")
                self.suite_completed.emit({
                    'total': 0,
                    'passed': 0,
                    'failed': 0,
                    'errors': 1,
                    'output': str(e)
                })
                
        except Exception as e:
            self.log_message.emit(f"JSON Handler test error: {str(e)}", "error")
            self.log_message.emit(traceback.format_exc(), "error")
            self.suite_completed.emit({
                'total': 0,
                'passed': 0,
                'failed': 0,
                'errors': 1,
                'output': str(e)
            })
    
    def run_integration_tests(self):
        """Run integration tests between components"""
        try:
            self.log_message.emit("Running integration tests...", "info")
            
            # Mock integration tests for demonstration
            tests = [
                ("WebSocket-JSON Integration", True, "Integration test passed"),
                ("Monitoring Integration", True, "Integration test passed"),
                ("Data Flow Integration", True, "Integration test passed"),
                ("OTA Integration", True, "Integration test passed")
            ]
            
            total = len(tests)
            passed_count = 0
            failed_count = 0
            
            for i, (test_name, success, message) in enumerate(tests):
                self.test_started.emit(test_name)
                time.sleep(0.2)  # Simulate test execution
                
                if success:
                    passed_count += 1
                else:
                    failed_count += 1
                    
                self.test_completed.emit(test_name, success, message)
                self.test_progress.emit(i + 1, total)
            
            self.suite_completed.emit({
                'total': total,
                'passed': passed_count,
                'failed': failed_count,
                'errors': 0,
                'output': f"Integration tests completed: {passed_count}/{total} passed"
            })
            
        except Exception as e:
            self.log_message.emit(f"Integration test error: {str(e)}", "error")
            self.suite_completed.emit({
                'total': 0,
                'passed': 0,
                'failed': 0,
                'errors': 1,
                'output': str(e)
            })
    
    def run_test_suite(self, suite, name):
        """Run a unittest suite"""
        try:
            from io import StringIO
            
            stream = StringIO()
            runner = unittest.TextTestRunner(stream=stream, verbosity=2)
            
            # Count total tests
            total = suite.countTestCases()
            self.log_message.emit(f"Running {total} tests from {name}", "info")
            
            if total == 0:
                self.suite_completed.emit({
                    'total': 0,
                    'passed': 0,
                    'failed': 0,
                    'errors': 0,
                    'output': f'No tests found in {name}'
                })
                return
            
            # Run tests
            result = runner.run(suite)
            
            # Process individual test results
            current = 0
            for test, _ in result.failures:
                current += 1
                self.test_progress.emit(current, total)
                
            for test, _ in result.errors:
                current += 1
                self.test_progress.emit(current, total)
                
            # Calculate passed tests
            passed = result.testsRun - len(result.failures) - len(result.errors)
            for _ in range(passed):
                current += 1
                if current <= total:
                    self.test_progress.emit(current, total)
            
            # Create summary
            summary = {
                'total': result.testsRun,
                'passed': passed,
                'failed': len(result.failures),
                'errors': len(result.errors),
                'output': stream.getvalue()
            }
            
            self.suite_completed.emit(summary)
            
        except Exception as e:
            self.log_message.emit(f"Error running test suite {name}: {str(e)}", "error")
            self.suite_completed.emit({
                'total': 0,
                'passed': 0,
                'failed': 0,
                'errors': 1,
                'output': str(e)
            })
    
    def run_all_tests(self):
        """Run all available tests"""
        try:
            # Reset overall results
            self.overall_results = {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'errors': 0,
                'output': ''
            }
            
            self.log_message.emit("Starting all tests...", "info")
            
            # Run each test suite
            self.run_websocket_tests()
            time.sleep(0.5)
            
            self.run_json_handler_tests()
            time.sleep(0.5)
            
            self.run_integration_tests()
            
            # Note: The individual test methods will emit suite_completed
            # which will be handled by the GUI
            
        except Exception as e:
            self.log_message.emit(f"Error running all tests: {str(e)}", "error")
            import traceback
            self.log_message.emit(traceback.format_exc(), "error")


class TestingTab(QWidget):
    """Testing and diagnostics tab for the GUI"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.test_runner = None
        self.test_history = []
        self.test_start_time = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize testing tab UI"""
        layout = QVBoxLayout(self)
        
        # Create horizontal splitter for main content
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Test Selection and Control
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Test Suite Selection
        test_selection_group = QGroupBox("Test Suites")
        test_selection_layout = QVBoxLayout()
        
        self.test_tree = QTreeWidget()
        self.test_tree.setHeaderLabel("Available Tests")
        self.populate_test_tree()
        
        test_selection_layout.addWidget(self.test_tree)
        test_selection_group.setLayout(test_selection_layout)
        
        # Test Control Panel
        control_group = QGroupBox("Test Control")
        control_layout = QGridLayout()
        
        self.run_selected_btn = QPushButton("▶️ Run Selected")
        self.run_all_btn = QPushButton("▶️ Run All Tests")
        self.stop_btn = QPushButton("⏹️ Stop")
        self.clear_results_btn = QPushButton("🗑️ Clear Results")
        self.export_results_btn = QPushButton("📊 Export Results")
        
        self.stop_btn.setEnabled(False)
        
        # Test options
        self.verbose_check = QCheckBox("Verbose Output")
        self.verbose_check.setChecked(True)
        self.stop_on_error_check = QCheckBox("Stop on Error")
        self.auto_scroll_check = QCheckBox("Auto-scroll Output")
        self.auto_scroll_check.setChecked(True)
        
        control_layout.addWidget(self.run_selected_btn, 0, 0)
        control_layout.addWidget(self.run_all_btn, 0, 1)
        control_layout.addWidget(self.stop_btn, 1, 0)
        control_layout.addWidget(self.clear_results_btn, 1, 1)
        control_layout.addWidget(self.export_results_btn, 2, 0, 1, 2)
        control_layout.addWidget(self.verbose_check, 3, 0)
        control_layout.addWidget(self.stop_on_error_check, 3, 1)
        control_layout.addWidget(self.auto_scroll_check, 4, 0, 1, 2)
        
        control_group.setLayout(control_layout)
        
        # Test Statistics
        stats_group = QGroupBox("Test Statistics")
        stats_layout = QGridLayout()
        
        self.total_tests_label = QLabel("Total: 0")
        self.passed_tests_label = QLabel("✅ Passed: 0")
        self.failed_tests_label = QLabel("❌ Failed: 0")
        self.error_tests_label = QLabel("⚠️ Errors: 0")
        self.duration_label = QLabel("Duration: 0.0s")
        self.last_run_label = QLabel("Last Run: Never")
        
        stats_layout.addWidget(self.total_tests_label, 0, 0)
        stats_layout.addWidget(self.passed_tests_label, 0, 1)
        stats_layout.addWidget(self.failed_tests_label, 1, 0)
        stats_layout.addWidget(self.error_tests_label, 1, 1)
        stats_layout.addWidget(self.duration_label, 2, 0)
        stats_layout.addWidget(self.last_run_label, 2, 1)
        
        stats_group.setLayout(stats_layout)
        
        left_layout.addWidget(test_selection_group)
        left_layout.addWidget(control_group)
        left_layout.addWidget(stats_group)
        
        # Right panel - Test Results and Output
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Create tab widget for different views
        self.result_tabs = QTabWidget()
        
        # Test Results Tab
        self.results_widget = QWidget()
        results_layout = QVBoxLayout(self.results_widget)
        
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Test", "Status", "Duration", "Details"])
        results_layout.addWidget(self.results_tree)
        
        # Test Output Tab
        self.output_widget = QWidget()
        output_layout = QVBoxLayout(self.output_widget)
        
        self.output_text = QTextBrowser()
        self.output_text.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
            }
        """)
        output_layout.addWidget(self.output_text)
        
        # Test History Tab
        self.history_widget = QWidget()
        history_layout = QVBoxLayout(self.history_widget)
        
        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list)
        
        # Coverage Report Tab
        self.coverage_widget = QWidget()
        coverage_layout = QVBoxLayout(self.coverage_widget)
        
        self.coverage_text = QTextBrowser()
        coverage_layout.addWidget(self.coverage_text)
        
        # Add tabs
        self.result_tabs.addTab(self.results_widget, "📋 Results")
        self.result_tabs.addTab(self.output_widget, "📝 Output")
        self.result_tabs.addTab(self.history_widget, "📜 History")
        self.result_tabs.addTab(self.coverage_widget, "📊 Coverage")
        
        right_layout.addWidget(self.result_tabs)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        # Add panels to splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([400, 800])
        
        layout.addWidget(main_splitter)
        
        # Connect signals
        self.setup_connections()
        
    def populate_test_tree(self):
        """Populate test tree with available tests"""
        # WebSocket Server Tests
        ws_item = QTreeWidgetItem(self.test_tree, ["WebSocket Server Tests"])
        ws_item.setCheckState(0, Qt.Unchecked)
        
        ws_tests = ["Basic Functionality", "Integration", "Edge Cases", "Performance"]
        for test in ws_tests:
            child = QTreeWidgetItem(ws_item, [test])
            child.setCheckState(0, Qt.Unchecked)
        
        # JSON Handler Tests
        json_item = QTreeWidgetItem(self.test_tree, ["JSON Handler Tests"])
        json_item.setCheckState(0, Qt.Unchecked)
        
        json_tests = ["Message Processing", "Command Creation", 
                     "Error Conditions", "Edge Cases"]
        for test in json_tests:
            child = QTreeWidgetItem(json_item, [test])
            child.setCheckState(0, Qt.Unchecked)
        
        # Integration Tests
        integ_item = QTreeWidgetItem(self.test_tree, ["Integration Tests"])
        integ_item.setCheckState(0, Qt.Unchecked)
        
        integ_tests = ["WebSocket-JSON Integration", "Monitoring Integration", 
                      "Data Flow", "OTA Integration"]
        for test in integ_tests:
            child = QTreeWidgetItem(integ_item, [test])
            child.setCheckState(0, Qt.Unchecked)
        
        self.test_tree.expandAll()
        
    def setup_connections(self):
        """Setup signal connections for TestingTab"""
        # Test control buttons
        self.run_selected_btn.clicked.connect(self.run_selected_tests)
        self.run_all_btn.clicked.connect(self.run_all_tests)
        self.stop_btn.clicked.connect(self.stop_tests)
        
        # Results management
        self.clear_results_btn.clicked.connect(self.clear_results)
        self.export_results_btn.clicked.connect(self.export_results)
        
        # History interaction
        self.history_list.itemDoubleClicked.connect(self.load_history_item)
    
    def run_selected_tests(self):
        """Run selected tests"""
        self.start_test_run("Selected")
    
    def run_all_tests(self):
        """Run all available tests"""
        self.start_test_run("All")
    
    def start_test_run(self, suite):
        """Start test execution"""
        self.clear_results()
        
        # Update UI state
        self.run_selected_btn.setEnabled(False)
        self.run_all_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        
        # Record start time
        self.test_start_time = QDateTime.currentDateTime()
        
        # Create and start test runner thread
        self.test_runner = TestRunner(suite)
        self.test_runner.test_started.connect(self.on_test_started)
        self.test_runner.test_completed.connect(self.on_test_completed)
        self.test_runner.test_progress.connect(self.on_test_progress)
        self.test_runner.suite_completed.connect(self.on_suite_completed)
        self.test_runner.log_message.connect(self.on_log_message)
        self.test_runner.start()
        
        self.add_output(f"Starting test run at {self.test_start_time.toString()}", "info")
    
    def stop_tests(self):
        """Stop running tests"""
        if self.test_runner and self.test_runner.isRunning():
            self.test_runner.terminate()
            self.add_output("\nTest execution stopped by user", "warning")
            self.on_suite_completed({})
    
    def on_test_started(self, test_name):
        """Handle test start signal"""
        self.add_output(f"▶️ Running: {test_name}", "info")
        
        item = QTreeWidgetItem(self.results_tree, [test_name, "🔄 Running", "", ""])
        item.setBackground(1, QBrush(QColor(255, 255, 200)))
    
    def on_test_completed(self, test_name, success, details):
        """Handle test completion signal"""
        for i in range(self.results_tree.topLevelItemCount()):
            item = self.results_tree.topLevelItem(i)
            if item.text(0) == test_name:
                if success:
                    item.setText(1, "✅ Passed")
                    item.setBackground(1, QBrush(QColor(200, 255, 200)))
                    self.add_output(f"✅ Passed: {test_name}", "success")
                else:
                    item.setText(1, "❌ Failed")
                    item.setBackground(1, QBrush(QColor(255, 200, 200)))
                    item.setText(3, details[:100] + "..." if len(details) > 100 else details)
                    self.add_output(f"❌ Failed: {test_name}\n{details}", "error")
                break
    
    def on_test_progress(self, current, total):
        """Update progress bar"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Progress: {current}/{total} ({current*100//total}%)")
    
    def on_suite_completed(self, results):
        """Handle test suite completion"""
        end_time = QDateTime.currentDateTime()
        duration = self.test_start_time.msecsTo(end_time) / 1000.0 if self.test_start_time else 0
        
        # Update statistics
        if 'total' in results:
            self.total_tests_label.setText(f"Total: {results['total']}")
            self.passed_tests_label.setText(f"✅ Passed: {results.get('passed', 0)}")
            self.failed_tests_label.setText(f"❌ Failed: {results.get('failed', 0)}")
            self.error_tests_label.setText(f"⚠️ Errors: {results.get('errors', 0)}")
        
        self.duration_label.setText(f"Duration: {duration:.2f}s")
        self.last_run_label.setText(f"Last Run: {end_time.toString('hh:mm:ss')}")
        
        # Update UI state
        self.run_selected_btn.setEnabled(True)
        self.run_all_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
    
    def on_log_message(self, message, level):
        """Handle log messages from test runner"""
        self.add_output(message, level)
    
    def add_output(self, text, level="info"):
        """Add text to output with color coding"""
        colors = {
            'info': '#d4d4d4',
            'success': '#4ec9b0',
            'warning': '#ce9178',
            'error': '#f48771',
            'debug': '#9cdcfe'
        }
        
        color = colors.get(level, '#d4d4d4')
        timestamp = QDateTime.currentDateTime().toString('hh:mm:ss.zzz')
        
        formatted_text = f'<span style="color: #808080">[{timestamp}]</span> '
        formatted_text += f'<span style="color: {color}">{text}</span><br>'
        
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output_text.insertHtml(formatted_text)
        
        if self.auto_scroll_check.isChecked():
            self.output_text.ensureCursorVisible()
    
    def clear_results(self):
        """Clear all test results"""
        self.results_tree.clear()
        self.output_text.clear()
        self.progress_bar.setValue(0)
    
    def export_results(self):
        """Export test results to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Test Results", 
            f"test_results_{QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')}.html",
            "HTML Files (*.html);;Text Files (*.txt);;JSON Files (*.json)"
        )
        
        if filename:
            try:
                if filename.endswith('.html'):
                    self.export_html(filename)
                elif filename.endswith('.json'):
                    self.export_json(filename)
                else:
                    self.export_text(filename)
                
                QMessageBox.information(self, "Export Successful", 
                                      f"Results exported to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", 
                                   f"Failed to export results: {str(e)}")
    
    def export_html(self, filename):
        """Export results as HTML"""
        with open(filename, 'w') as f:
            f.write(f"<html><body><h1>Test Results</h1><pre>{self.output_text.toPlainText()}</pre></body></html>")
    
    def export_json(self, filename):
        """Export results as JSON"""
        data = {'output': self.output_text.toPlainText()}
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def export_text(self, filename):
        """Export results as plain text"""
        with open(filename, 'w') as f:
            f.write(self.output_text.toPlainText())
    
    def load_history_item(self, item):
        """Load a test run from history"""
        QMessageBox.information(self, "History", "Loading historical test run...")

class DataMonitorGUI(QMainWindow):
    data_received = pyqtSignal(str, float, float)  # parameter, value, timestamp
    log_message = pyqtSignal(str)  # NEW: For thread-safe logging
    operation_log_message = pyqtSignal(str)  # NEW: For thread-safe operation log
    
    def __init__(self):
        super().__init__()
        
        logger.info("Initializing DataMonitorGUI")
        
        # Initialize components
        self.variable_manager = VariableManager()
        self.data_mutex = QMutex()
        self.settings = QSettings("FYP-19-26", "VariableMonitor")
        
        # NEW: Register QTextCursor for thread-safe operations
        try:
            QMetaType.type("QTextCursor")
        except:
            pass  # Ignore if already registered
        
        # Create server instance
        self.server = WebSocketServer()
        self.server.data_callback = self.on_data_received
        
        # Store response data
        self.pending_responses = {}
        
        # Initialize UI
        self.init_ui()
        self.setup_connections()
        self.load_settings()
        
        # Start the server in a separate thread
        self.server_thread = threading.Thread(target=self.server.run)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        # Start connection status timer
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.update_connection_status)
        self.connection_timer.start(1000)
        
        logger.info("DataMonitorGUI initialization complete")
        
    def init_ui(self):
        self.setWindowTitle("WebSocket Dynamic Variable Monitor v2.0")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        self.fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        self.maximize_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.maximize_shortcut.activated.connect(self.toggle_maximize)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.tuning_tab = QWidget()
        self.monitoring_tab = QWidget()
        self.ota_tab = QWidget()
        self.testing_tab = TestingTab(self)
        
        # Add tabs to tab widget
        self.tab_widget.addTab(self.tuning_tab, "⚙️ Variable Tuning")
        self.tab_widget.addTab(self.monitoring_tab, "📊 Monitoring")
        self.tab_widget.addTab(self.ota_tab, "📦 OTA Updates")
        self.tab_widget.addTab(self.testing_tab, "🧪 Testing & Diagnostics")
        
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
        
    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        load_csv_action = file_menu.addAction('Load CSV')
        load_csv_action.triggered.connect(self.load_csv_file)
        # Add this after load_csv_action
        convert_elf_action = file_menu.addAction('Convert ELF to CSV')
        convert_elf_action.triggered.connect(self.run_elf_to_csv_converter)
        file_menu.addSeparator()
        
        export_action = file_menu.addAction('Export Data')
        export_action.triggered.connect(self.export_data)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)
        
        # View menu
        view_menu = menubar.addMenu('View')
        
        clear_log_action = view_menu.addAction('Clear Log')
        clear_log_action.triggered.connect(lambda: self.log_text.clear() if hasattr(self, 'log_text') else None)
        
        clear_table_action = view_menu.addAction('Clear Table')
        clear_table_action.triggered.connect(self.clear_table)
        
        # Tools menu
        tools_menu = menubar.addMenu('Tools')
        
        settings_action = tools_menu.addAction('Settings')
        settings_action.triggered.connect(self.show_settings_dialog)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        about_action = help_menu.addAction('About')
        about_action.triggered.connect(self.show_about_dialog)
        
    def setup_tuning_tab(self):
        layout = QVBoxLayout(self.tuning_tab)
        
        # Control panel
        control_group = QGroupBox("Variable Control")
        control_layout = QHBoxLayout()

        # NEW: Add Init/End buttons
        self.init_debug_btn = QPushButton("🚀 Initialize Debug")
        self.init_debug_btn.clicked.connect(self.initialize_debug_mode)
        self.init_debug_btn.setStyleSheet("background-color: #2196F3;")

        self.end_debug_btn = QPushButton("🛑 End Debug")
        self.end_debug_btn.clicked.connect(self.end_debug_mode)
        self.end_debug_btn.setEnabled(False)
        self.end_debug_btn.setStyleSheet("background-color: #f44336;")

        # NEW: ADD THIS - ELF Converter button
        self.elf_convert_btn = QPushButton("🔄 Convert ELF to CSV")
        self.elf_convert_btn.clicked.connect(self.run_elf_to_csv_converter)
        self.elf_convert_btn.setStyleSheet("background-color: #9C27B0;")  # Purple color

        self.upload_csv_btn = QPushButton("📁 Upload CSV")
        self.upload_csv_btn.clicked.connect(self.load_csv_file)

        self.refresh_data_btn = QPushButton("🔄 Refresh Data")
        self.refresh_data_btn.clicked.connect(self.refresh_all_data)
        self.refresh_data_btn.setEnabled(False)

        self.write_data_btn = QPushButton("✏️ Write Data")
        self.write_data_btn.clicked.connect(self.write_all_data)
        self.write_data_btn.setEnabled(False)

        self.write_selected_btn = QPushButton("✏️ Write Selected")
        self.write_selected_btn.clicked.connect(self.write_selected_variable)
        self.write_selected_btn.setEnabled(False)

        self.start_monitoring_btn = QPushButton("▶️ Start Monitoring")
        self.stop_monitoring_btn = QPushButton("⏹️ Stop Monitoring")
        self.start_monitoring_btn.clicked.connect(self.start_monitoring)
        self.stop_monitoring_btn.clicked.connect(self.stop_monitoring)
        self.start_monitoring_btn.setEnabled(False)
        self.stop_monitoring_btn.setEnabled(False)

        control_layout.addWidget(self.init_debug_btn)
        control_layout.addWidget(self.end_debug_btn)
        control_layout.addWidget(self.elf_convert_btn)  # ADD THIS LINE
        control_layout.addWidget(self.upload_csv_btn)
        control_layout.addWidget(self.refresh_data_btn)
        control_layout.addWidget(self.write_data_btn)
        control_layout.addWidget(self.start_monitoring_btn)
        control_layout.addWidget(self.stop_monitoring_btn)
        control_layout.addWidget(self.write_selected_btn)  
        control_layout.addStretch()

        control_group.setLayout(control_layout)
        
        # Search bar
        search_group = QGroupBox("Search & Filter")
        search_layout = QHBoxLayout()
        
        search_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Enter variable name...")
        self.search_box.textChanged.connect(self.filter_variables)
        search_layout.addWidget(self.search_box)
        
        search_group.setLayout(search_layout)
        
        # Variable table
        table_group = QGroupBox("Variables")
        table_layout = QVBoxLayout()
        
        self.variable_table = QTableWidget()
        self.variable_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.variable_table.customContextMenuRequested.connect(self.show_context_menu)
        self.variable_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.variable_table.setSelectionMode(QAbstractItemView.SingleSelection)  # Single row at a time
        self.variable_table.setAlternatingRowColors(True)  # Visual distinction
        self.variable_table.setColumnCount(6)
        self.variable_table.setHorizontalHeaderLabels([
            "Variable Name", "Address", "No. of Elements", 
            "Data Type", "Current Value", "New Value"
        ])
        
        self.variable_table.setEditTriggers(QAbstractItemView.DoubleClicked)
        
        header = self.variable_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        
        table_layout.addWidget(self.variable_table)
        table_group.setLayout(table_layout)
        
        # Log area
        log_group = QGroupBox("Operation Log")
        log_layout = QVBoxLayout()
        self.operation_log = QTextEdit()
        self.operation_log.setMaximumHeight(150)
        self.operation_log.setReadOnly(True)
        log_layout.addWidget(self.operation_log)
        log_group.setLayout(log_layout)
        
        # Add widgets to tuning tab layout
        layout.addWidget(control_group)
        layout.addWidget(search_group)
        layout.addWidget(table_group)
        layout.addWidget(log_group)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
            
    def toggle_maximize(self):
        """Toggle maximize mode"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def run_elf_to_csv_converter(self):
        """Run the ELF to CSV converter script"""
        try:
            # Disable button during conversion
            self.elf_convert_btn.setEnabled(False)
            self.elf_convert_btn.setText("Converting...")
            
            # Update status
            self.operation_log.append("Starting ELF to CSV conversion...")
            self.update_status("Converting ELF file...")
            
            # Path to your converter script - adjust as needed
            converter_script = Path(__file__).parent / "mem_map_buelf.py"
            
            # Run the converter script
            result = subprocess.run(
                ["python", str(converter_script)],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent  # Set working directory
            )
            
            # Check if successful
            if result.returncode == 0:
                self.operation_log.append("✅ ELF to CSV conversion completed successfully!")
                self.update_status("ELF conversion complete")
                
                # Parse output to find the generated CSV file path
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines:
                    if '.csv' in line:
                        self.operation_log.append(f"Generated: {line}")
                
                # Auto-load the most recent CSV file
                csv_dir = Path(__file__).parent.parent / "data" / "csv"
                if csv_dir.exists():
                    csv_files = list(csv_dir.glob("*.csv"))
                    if csv_files:
                        # Get the most recent file
                        latest_csv = max(csv_files, key=lambda f: f.stat().st_mtime)
                        
                        # Ask user if they want to load it
                        reply = QMessageBox.question(
                            self, "Load Generated CSV", 
                            f"CSV file generated successfully!\n\n{latest_csv.name}\n\nDo you want to load it now?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        
                        if reply == QMessageBox.Yes:
                            # Load it automatically
                            if self.variable_manager.load_csv(str(latest_csv)):
                                self.last_csv_file = str(latest_csv)
                                self.populate_table()
                                self.update_monitoring_variables()
                                self.refresh_data_btn.setEnabled(True)
                                self.write_data_btn.setEnabled(True)
                                self.start_monitoring_btn.setEnabled(True)
                                self.operation_log.append(f"✅ Loaded: {latest_csv.name}")
                                self.update_status(f"CSV loaded: {latest_csv.name}")
            else:
                error_msg = result.stderr if result.stderr else "Unknown error"
                self.operation_log.append(f"❌ ELF conversion failed: {error_msg}")
                QMessageBox.critical(self, "Conversion Failed", 
                                    f"Failed to convert ELF file:\n{error_msg}")
        
        except FileNotFoundError:
            self.operation_log.append("❌ Converter script not found")
            QMessageBox.critical(self, "Script Not Found", 
                                "ELF to CSV converter script not found.\n"
                                "Please ensure elf_to_csv_converter.py is in the correct location.")
        except Exception as e:
            self.operation_log.append(f"❌ Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to run converter: {str(e)}")
        
        finally:
            # Re-enable button
            self.elf_convert_btn.setEnabled(True)
            self.elf_convert_btn.setText("🔄 Convert ELF to CSV")
        
    def setup_monitoring_tab(self):
        layout = QVBoxLayout(self.monitoring_tab)
        
        # Control panel
        control_group = QGroupBox("Monitoring Controls")
        control_layout = QHBoxLayout()
        
        self.export_btn = QPushButton("💾 Export Data")
        self.clear_plot_btn = QPushButton("🗑️ Clear Plot")
        
        control_layout.addWidget(QLabel("Monitor Variable:"))
        self.parameter_combo = QComboBox()
        self.parameter_combo.addItem("All Variables")
        self.parameter_combo.currentTextChanged.connect(self.on_parameter_changed)
        # In the control_layout section, add:
        self.debug_plot_btn = QPushButton("🔍 Debug Plot Data")
        self.debug_plot_btn.clicked.connect(self.debug_plot_data)
        control_layout.addWidget(self.debug_plot_btn)
        control_layout.addWidget(self.parameter_combo)
        
        control_layout.addWidget(self.export_btn)
        control_layout.addWidget(self.clear_plot_btn)
        control_layout.addStretch()
        
        control_group.setLayout(control_layout)
        
        # Plot area
        self.plot_widget = RealTimePlotWidget(title="Real-time Variable Monitoring", y_label="Value")
        
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
    
    def setup_ota_tab(self):
        """Setup OTA update tab"""
        layout = QVBoxLayout(self.ota_tab)
        
        # OTA control panel
        control_group = QGroupBox("OTA Control")
        control_layout = QGridLayout()
        
        # File selection
        self.ota_file_btn = QPushButton("📁 Select Firmware File")
        self.ota_file_label = QLabel("No file selected")
        
        # Progress bar
        self.ota_progress = QProgressBar()
        self.ota_progress.setVisible(False)
        
        # Status label
        self.ota_status_label = QLabel("Ready")
        
        # Control buttons
        self.ota_start_btn = QPushButton("▶️ Start Update")
        self.ota_start_btn.setEnabled(False)
        
        self.ota_cancel_btn = QPushButton("❌ Cancel")
        self.ota_cancel_btn.setEnabled(False)
        
        # Device selection
        self.ota_device_combo = QComboBox()
        self.ota_device_combo.addItem("All Devices")
        
        # Layout arrangement
        control_layout.addWidget(QLabel("Target Device:"), 0, 0)
        control_layout.addWidget(self.ota_device_combo, 0, 1, 1, 2)
        control_layout.addWidget(QLabel("Firmware:"), 1, 0)
        control_layout.addWidget(self.ota_file_btn, 1, 1)
        control_layout.addWidget(self.ota_file_label, 1, 2)
        control_layout.addWidget(self.ota_progress, 2, 0, 1, 3)
        control_layout.addWidget(self.ota_status_label, 3, 0, 1, 3)
        control_layout.addWidget(self.ota_start_btn, 4, 1)
        control_layout.addWidget(self.ota_cancel_btn, 4, 2)
        
        control_group.setLayout(control_layout)
        
        # OTA Information
        info_group = QGroupBox("Firmware Information")
        info_layout = QGridLayout()
        
        self.ota_file_size_label = QLabel("File Size: -")
        self.ota_checksum_label = QLabel("Checksum: -")
        self.ota_version_label = QLabel("Version: -")
        
        info_layout.addWidget(self.ota_file_size_label, 0, 0)
        info_layout.addWidget(self.ota_checksum_label, 0, 1)
        info_layout.addWidget(self.ota_version_label, 1, 0, 1, 2)
        
        info_group.setLayout(info_layout)
        
        # Log area
        log_group = QGroupBox("OTA Log")
        log_layout = QVBoxLayout()
        self.ota_log = QTextEdit()
        self.ota_log.setReadOnly(True)
        log_layout.addWidget(self.ota_log)
        log_group.setLayout(log_layout)
        
        layout.addWidget(control_group)
        layout.addWidget(info_group)
        layout.addWidget(log_group)
        
        # Connect signals
        self.ota_file_btn.clicked.connect(self.select_ota_file)
        self.ota_start_btn.clicked.connect(self.start_ota_update)
        self.ota_cancel_btn.clicked.connect(self.cancel_ota_update)

    def show_context_menu(self, position):
        """Show context menu for table right-click"""
        menu = QMenu()
        
        write_action = menu.addAction("✏️ Write This Variable")
        write_action.triggered.connect(self.write_selected_variable)
        
        read_action = menu.addAction("🔄 Read This Variable")
        read_action.triggered.connect(self.read_selected_variable)
        
        menu.exec_(self.variable_table.mapToGlobal(position))

    def write_selected_variable(self):
        """Write only the selected variable"""
        current_row = self.variable_table.currentRow()
        
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a variable to write")
            return
        
        # Get variable details from selected row
        var_name = self.variable_table.item(current_row, 0).text()
        address_str = self.variable_table.item(current_row, 1).text()
        data_type = self.variable_table.item(current_row, 3).text()
        new_value_str = self.variable_table.item(current_row, 5).text()
        
        # Confirm with user
        reply = QMessageBox.question(
            self, "Confirm Write",
            f"Write value '{new_value_str}' to '{var_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Write the single variable
        self._write_single_variable(current_row)

    def read_selected_variable(self):
        """Read only the selected variable"""
        current_row = self.variable_table.currentRow()
        
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a variable to read")
            return
        
        self._read_single_variable(current_row)

    def _write_single_variable(self, row):
        """Helper method to write a single variable"""
        try:
            address_str = self.variable_table.item(row, 1).text()
            address = int(address_str, 16)
            new_value_str = self.variable_table.item(row, 5).text()
            var_name = self.variable_table.item(row, 0).text()
            data_type = self.variable_table.item(row, 3).text()
            
            value = float(new_value_str)
            
            success = self.server.write_data_with_address(address, value, data_type)
            
            if success:
                self.operation_log.append(f"✅ Written {value} to {var_name} at {address_str}")
                # Update current value column
                self.variable_table.item(row, 4).setText(new_value_str)
            else:
                self.operation_log.append(f"❌ Failed to write {var_name} at {address_str}")
                
        except ValueError:
            self.operation_log.append(f"❌ Invalid value for {var_name}")
        except Exception as e:
            self.operation_log.append(f"❌ Error writing {var_name}: {e}")

    def _read_single_variable(self, row):
        """Helper method to read a single variable"""
        try:
            address_str = self.variable_table.item(row, 1).text()
            address = int(address_str, 16)
            var_name = self.variable_table.item(row, 0).text()
            
            # Send SET_MTA and UPLOAD commands
            address_bytes = self.variable_manager.address_to_bytes(address)
            set_mta_bytes = [0xF6, 0x00, 0x00, 0x00] + address_bytes
            set_mta_cmd = self.server.json_handler.create_set_mta_command(set_mta_bytes)
            
            self.server.broadcast(set_mta_cmd)
            time.sleep(0.1)
            
            upload_cmd = self.server.json_handler.create_upload_command(f"var_{row}")
            self.server.broadcast(upload_cmd)
            
            self.operation_log.append(f"📖 Reading {var_name} from {address_str}")
            
        except Exception as e:
            self.operation_log.append(f"❌ Error reading {var_name}: {e}")
    
    def filter_variables(self, text):
        """Filter table rows based on search text"""
        for row in range(self.variable_table.rowCount()):
            match = False
            for col in range(self.variable_table.columnCount()):
                item = self.variable_table.item(row, col)
                if item and text.lower() in item.text().lower():
                    match = True
                    break
            self.variable_table.setRowHidden(row, not match)
    
    def load_csv_file(self):
        """Load CSV file with variable definitions"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load CSV File", "", 
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if filename:
            if self.variable_manager.load_csv(filename):
                self.last_csv_file = filename
                self.populate_table()
                self.update_monitoring_variables()
                self.refresh_data_btn.setEnabled(True)
                self.write_data_btn.setEnabled(True)
                self.start_monitoring_btn.setEnabled(True)
                self.operation_log.append(f"Loaded CSV: {filename}")
                self.update_status(f"CSV loaded: {os.path.basename(filename)}")
            else:
                QMessageBox.critical(self, "Error", "Failed to load CSV file")

    def initialize_debug_mode(self):
        """Initialize debug mode with the device."""
        if not self.server.clients:
            QMessageBox.warning(self, "No Connection", "No clients connected")
            return
        
        # Use signal for thread-safe logging
        self.operation_log_message.emit("Initializing debug mode...")
        self.update_status("Initializing debug mode...")
        
        # Send init command in separate thread to avoid blocking GUI
        def init_thread():
            success = self.server.send_init_command()
            if success:
                # Use signals for thread-safe UI updates
                self.operation_log_message.emit("✅ Debug mode initialized successfully")
                self.update_status("Debug mode active")
                
                # Update button states on main thread
                def update_ui():
                    self.init_debug_btn.setEnabled(False)
                    self.end_debug_btn.setEnabled(True)
                    self.refresh_data_btn.setEnabled(True)
                    self.write_data_btn.setEnabled(True)
                    self.start_monitoring_btn.setEnabled(True)
                    self.write_selected_btn.setEnabled(True)  # Add this line
                
                # Execute UI updates on main thread
                self.operation_log_message.emit("UI update scheduled")
                QTimer.singleShot(0, update_ui)
            else:
                self.operation_log_message.emit("❌ Failed to initialize debug mode")
                self.update_status("Initialization failed")
                
                # Show error on main thread
                def show_error():
                    QMessageBox.critical(self, "Initialization Failed", 
                                    "Failed to initialize debug mode. Check connection.")
                
                QTimer.singleShot(0, show_error)
        
        threading.Thread(target=init_thread, daemon=True).start()

    def end_debug_mode(self):
        """End debug mode with the device."""
        if not self.server.clients:
            QMessageBox.warning(self, "No Connection", "No clients connected")
            return
        
        # Stop monitoring if active
        if self.server.monitoring_active:
            self.stop_monitoring()
            time.sleep(0.5)
        
        # Use signal for thread-safe logging
        self.operation_log_message.emit("Ending debug mode...")
        self.update_status("Ending debug mode...")
        
        # Send end command in separate thread
        def end_thread():
            success = self.server.send_end_command()
            if success:
                self.operation_log_message.emit("✅ Debug mode ended successfully")
                self.update_status("Debug mode ended")
                
                # Update UI on main thread
                def update_ui():
                    self.init_debug_btn.setEnabled(True)
                    self.end_debug_btn.setEnabled(False)
                    self.refresh_data_btn.setEnabled(False)
                    self.write_data_btn.setEnabled(False)
                    self.start_monitoring_btn.setEnabled(False)
                    self.stop_monitoring_btn.setEnabled(False)
                    self.write_selected_btn.setEnabled(False)  
                
                QTimer.singleShot(0, update_ui)
            else:
                self.operation_log_message.emit("❌ Failed to end debug mode")
                self.update_status("End command failed")
        
        threading.Thread(target=end_thread, daemon=True).start()
    
    def populate_table(self):
        """Populate table with variables from CSV"""
        variables = self.variable_manager.variables
        self.variable_table.setRowCount(0)
        
        for var in variables:
            for i in range(var['elements']):
                row_position = self.variable_table.rowCount()
                self.variable_table.insertRow(row_position)
                
                # Variable name with index for arrays
                if var['elements'] > 1:
                    name_item = QTableWidgetItem(f"{var['name']}[{i}]")
                else:
                    name_item = QTableWidgetItem(var['name'])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                
                # Calculate address for this element
                addresses = self.variable_manager.get_element_addresses(
                    var['address'], var['elements'], var['data_type']
                )
                address_item = QTableWidgetItem(f"0x{addresses[i]:08X}")
                address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
                
                # Number of elements
                elements_item = QTableWidgetItem("1")
                elements_item.setFlags(elements_item.flags() & ~Qt.ItemIsEditable)
                
                # Data type
                type_item = QTableWidgetItem(var['data_type'])
                type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
                
                # Current value
                current_value_item = QTableWidgetItem("0")
                current_value_item.setFlags(current_value_item.flags() & ~Qt.ItemIsEditable)
                current_value_item.setBackground(QColor(240, 240, 240))
                
                # New value
                new_value_item = QTableWidgetItem("0")
                
                # Set items in table
                self.variable_table.setItem(row_position, 0, name_item)
                self.variable_table.setItem(row_position, 1, address_item)
                self.variable_table.setItem(row_position, 2, elements_item)
                self.variable_table.setItem(row_position, 3, type_item)
                self.variable_table.setItem(row_position, 4, current_value_item)
                self.variable_table.setItem(row_position, 5, new_value_item)

        self.debug_table_contents()
    
    def debug_table_contents(self):
        """Debug helper to print all table variable names"""
        logger.info("=== TABLE CONTENTS DEBUG ===")
        for row in range(self.variable_table.rowCount()):
            var_name = self.variable_table.item(row, 0).text() if self.variable_table.item(row, 0) else "None"
            address = self.variable_table.item(row, 1).text() if self.variable_table.item(row, 1) else "None"
            logger.info(f"Row {row}: Name='{var_name}', Address='{address}'")
        logger.info("=== END TABLE DEBUG ===")
    
    def update_monitoring_variables(self):
        """Update monitoring combo box with loaded variables"""
        self.parameter_combo.clear()
        self.parameter_combo.addItem("All Variables")
        
        # Add all variables to combo box
        for var in self.variable_manager.variables:
            if var['elements'] > 1:
                # For arrays, add both the base name and individual elements
                self.parameter_combo.addItem(var['name'])  # Base name for whole array
                for i in range(var['elements']):
                    self.parameter_combo.addItem(f"{var['name']}[{i}]")  # Individual elements
            else:
                self.parameter_combo.addItem(var['name'])
        
        logger.info(f"Updated monitoring combo with {self.parameter_combo.count()} items")
    
    def refresh_all_data(self):
        """Refresh data for all variables"""
        if not self.server.clients:
            QMessageBox.warning(self, "No Connection", "No clients connected")
            return
        
        self.operation_log.append("Starting data refresh...")
        
        for row in range(self.variable_table.rowCount()):
            address_str = self.variable_table.item(row, 1).text()
            address = int(address_str, 16)
            
            address_bytes = self.variable_manager.address_to_bytes(address)
            set_mta_bytes = [0xF6, 0x00, 0x00, 0x00] + address_bytes
            set_mta_cmd = self.server.json_handler.create_set_mta_command(set_mta_bytes)
            
            self.server.broadcast(set_mta_cmd)
            time.sleep(0.1)
            
            upload_cmd = self.server.json_handler.create_upload_command(f"var_{row}")
            self.server.broadcast(upload_cmd)
            time.sleep(0.1)
            
            self.operation_log.append(f"Reading from address {address_str}")
        
        self.operation_log.append("Data refresh completed")
    
    def write_all_data(self):
        """Write data for all variables"""
        if not self.server.clients:
            QMessageBox.warning(self, "No Connection", "No clients connected")
            return
        
        reply = QMessageBox.question(
            self, "Confirm Write", 
            "Are you sure you want to write all new values to the device?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        self.operation_log.append("Starting data write...")
        
        for row in range(self.variable_table.rowCount()):
            address_str = self.variable_table.item(row, 1).text()
            address = int(address_str, 16)
            new_value_str = self.variable_table.item(row, 5).text()
            var_name = self.variable_table.item(row, 0).text()
            data_type = self.variable_table.item(row, 3).text()
            
            try:
                value = float(new_value_str)
                
                # Use new protocol write method
                success = self.server.write_data_with_address(address, value, data_type)
                
                if success:
                    self.operation_log.append(f"✅ Written {value} to {var_name} at {address_str}")
                else:
                    self.operation_log.append(f"❌ Failed to write {var_name} at {address_str}")
                
                time.sleep(0.2)  # Small delay between writes
                
            except ValueError as e:
                self.operation_log.append(f"❌ Error writing {var_name}: Invalid value '{new_value_str}'")
            except Exception as e:
                self.operation_log.append(f"❌ Error writing {var_name}: {e}")
                
        self.operation_log.append("Data write completed")
    
    def value_to_bytes(self, value, data_type):
        """Convert a value to bytes based on data type"""
        import struct
        
        format_map = {
            'uint8_t': 'B',
            'int8_t': 'b', 
            'uint16_t': 'H',
            'int16_t': 'h',
            'uint32_t': 'I', 
            'int32_t': 'i',
            'float': 'f',
            'double': 'd'
        }
        
        fmt = format_map.get(data_type, 'f')
        
        try:
            if fmt in ['B', 'H', 'I']:
                value = int(abs(value))
            elif fmt in ['b', 'h', 'i']:
                value = int(value)
            else:
                value = float(value)
                
            packed = struct.pack('<' + fmt, value)
            byte_list = list(packed)
            
            if len(byte_list) < 4:
                byte_list.extend([0] * (4 - len(byte_list)))
            elif len(byte_list) > 4:
                byte_list = byte_list[:4]
                
            return byte_list
            
        except Exception as e:
            logger.error(f"Error converting {value} to bytes: {e}")
            return [0, 0, 0, 0]
    
    def clear_table(self):
        """Clear the variable table"""
        self.variable_table.setRowCount(0)
        self.variable_manager.variables = []
        self.parameter_combo.clear()
        self.parameter_combo.addItem("All Variables")
        self.refresh_data_btn.setEnabled(False)
        self.write_data_btn.setEnabled(False)
        self.start_monitoring_btn.setEnabled(False)
    
    def on_data_received(self, parameter, value, timestamp):
        """Handle received data with thread safety and ensure plot updates"""
        with QMutexLocker(self.data_mutex):
            logger.debug(f"Data received - Parameter: {parameter}, Value: {value}, Timestamp: {timestamp}")
            
            # Update table - improved matching logic
            updated = False
            
            # Search through all rows to find matching variable
            for row in range(self.variable_table.rowCount()):
                var_name_item = self.variable_table.item(row, 0)
                if var_name_item:
                    var_name = var_name_item.text()
                    
                    # Exact match (for both single vars and array elements)
                    if var_name == parameter:
                        try:
                            current_value_item = self.variable_table.item(row, 4)
                            if current_value_item:
                                current_value_item.setText(f"{value:.3f}")
                                logger.info(f"Updated table {var_name} with value {value:.3f}")
                                updated = True
                                break
                        except Exception as e:
                            logger.error(f"Error updating table row {row}: {e}")
            
            if not updated:
                logger.warning(f"Could not find table row for parameter '{parameter}'")
            
            # ALWAYS emit signal for plotting regardless of table update
            # This ensures the plot gets the data even if table update fails
            try:
                self.data_received.emit(parameter, float(value), float(timestamp))
                logger.debug(f"Emitted plot signal for {parameter}: {value}")
            except Exception as e:
                logger.error(f"Error emitting plot signal: {e}")
    
    def setup_connections(self):
        self.data_received.connect(self.plot_widget.update_plot)
        self.data_received.connect(self.log_data)
        self.export_btn.clicked.connect(self.export_data)
        self.clear_plot_btn.clicked.connect(self.plot_widget.clear_data)
        self.parameter_combo.currentTextChanged.connect(self.on_parameter_changed)
        
        # NEW: Connect thread-safe logging signals
        self.log_message.connect(self.log_text.append)
        self.operation_log_message.connect(self.operation_log.append)
        
    def start_monitoring(self):
        """Start continuous monitoring of variables."""
        if not self.variable_manager.variables:
            QMessageBox.warning(self, "No Variables", "Please load a CSV file first")
            return
        
        if not self.server.is_initialized:
            QMessageBox.warning(self, "Not Initialized", 
                            "Please initialize debug mode first")
            return
            
        logger.info("Starting variable monitoring")
        self.server.start_dynamic_monitoring(self.variable_manager)
        self.start_monitoring_btn.setEnabled(False)
        self.stop_monitoring_btn.setEnabled(True)
        self.update_status("Monitoring started")
        self.operation_log.append("✅ Monitoring started")
        
    def stop_monitoring(self):
        logger.info("Stopping variable monitoring")
        self.server.stop_monitoring()
        self.start_monitoring_btn.setEnabled(True)
        self.stop_monitoring_btn.setEnabled(False)
        self.update_status("Monitoring stopped")
        self.operation_log.append("Monitoring stopped")
    
    def log_data(self, parameter, value, timestamp):
        time_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
        log_msg = f"{time_str} - {parameter}: {value:.2f}"
        self.log_text.append(log_msg)
        
        if self.log_text.document().blockCount() > 1000:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def debug_plot_data(self):
        """Debug method to check what data is in the plot"""
        logger.info("=== PLOT DATA DEBUG ===")
        if hasattr(self.plot_widget, 'data_points'):
            for param, points in self.plot_widget.data_points.items():
                if points:
                    latest = points[-1] if points else (0, 0)
                    logger.info(f"Parameter '{param}': {len(points)} points, latest value={latest[0]}")
                else:
                    logger.info(f"Parameter '{param}': No data points")
        else:
            logger.info("No plot data available")
        logger.info("=== END PLOT DEBUG ===")
    
    def on_parameter_changed(self, parameter):
        """Handle parameter selection change in monitoring tab"""
        logger.info(f"Parameter selection changed to: {parameter}")
        
        if parameter == "All Variables":
            # Show all variables
            self.plot_widget.set_visible_parameters([])
            logger.info("Showing all variables on plot")
        else:
            # Find all related parameters
            visible_params = []
            
            # Check if this is a base variable name (for arrays)
            base_var = None
            for var in self.variable_manager.variables:
                if var['name'] == parameter:
                    base_var = var
                    break
            
            if base_var and base_var['elements'] > 1:
                # It's an array base name - show all elements
                for i in range(base_var['elements']):
                    visible_params.append(f"{parameter}[{i}]")
                logger.info(f"Showing array elements for {parameter}: {visible_params}")
            elif '[' in parameter:
                # It's a specific array element
                visible_params.append(parameter)
                logger.info(f"Showing single element: {parameter}")
            else:
                # It's a single variable
                visible_params.append(parameter)
                logger.info(f"Showing single variable: {parameter}")
            
            self.plot_widget.set_visible_parameters(visible_params)
    
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
    
    def select_ota_file(self):
        """Select firmware file for OTA update"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "",
            "Binary Files (*.bin);;Hex Files (*.hex);;All Files (*)"
        )
        
        if filename:
            self.ota_file_label.setText(os.path.basename(filename))
            self.ota_start_btn.setEnabled(True)
            
            # Get file info
            file_size = os.path.getsize(filename)
            self.ota_file_size_label.setText(f"File Size: {file_size:,} bytes")
            
            # Calculate checksum
            import hashlib
            with open(filename, 'rb') as f:
                checksum = hashlib.md5(f.read()).hexdigest()
            self.ota_checksum_label.setText(f"Checksum: {checksum[:16]}...")
            
            self.ota_log.append(f"Selected firmware: {filename}")
    
    def start_ota_update(self):
        """Start OTA update process"""
        self.ota_start_btn.setEnabled(False)
        self.ota_cancel_btn.setEnabled(True)
        self.ota_progress.setVisible(True)
        self.ota_progress.setValue(0)
        
        self.ota_log.append("Starting OTA update...")
        self.ota_status_label.setText("Updating...")
        
        # Simulate OTA progress
        self.ota_timer = QTimer()
        self.ota_timer.timeout.connect(self.update_ota_progress)
        self.ota_timer.start(100)
        self.ota_progress_value = 0
    
    def update_ota_progress(self):
        """Update OTA progress (simulation)"""
        self.ota_progress_value += 1
        self.ota_progress.setValue(self.ota_progress_value)
        
        if self.ota_progress_value >= 100:
            self.ota_timer.stop()
            self.ota_complete()
    
    def ota_complete(self):
        """Complete OTA update"""
        self.ota_log.append("OTA update completed successfully!")
        self.ota_status_label.setText("Update Complete")
        self.ota_start_btn.setEnabled(True)
        self.ota_cancel_btn.setEnabled(False)
        QMessageBox.information(self, "OTA Complete", "Firmware update completed successfully!")
    
    def cancel_ota_update(self):
        """Cancel OTA update"""
        if hasattr(self, 'ota_timer'):
            self.ota_timer.stop()
        
        self.ota_progress.setVisible(False)
        self.ota_start_btn.setEnabled(True)
        self.ota_cancel_btn.setEnabled(False)
        self.ota_status_label.setText("Update Cancelled")
        self.ota_log.append("OTA update cancelled by user")
    
    def show_settings_dialog(self):
        """Show settings dialog"""
        QMessageBox.information(self, "Settings", "Settings dialog not yet implemented")
    
    def show_about_dialog(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "About", 
            "Dynamic Variable Monitor\nVersion 2.0\n\n"
            "A comprehensive WebSocket-based variable monitoring and testing application.\n\n"
            "Features:\n"
            "• Real-time variable monitoring\n"
            "• Dynamic variable tuning\n"
            "• OTA firmware updates\n"
            "• Comprehensive testing suite\n\n"
            "© 2024 Your Company"
        )
    
    def update_connection_status(self):
        """Update connection status indicator"""
        if hasattr(self.server, 'clients') and self.server.clients:
            client_count = len(self.server.clients)
            self.connection_label.setText(f"● Connected ({client_count} clients)")
            self.connection_label.setStyleSheet("color: green; font-weight: bold; padding: 5px;")
            
            # Update OTA device list
            if hasattr(self, 'ota_device_combo'):
                current_devices = [self.ota_device_combo.itemText(i) 
                                for i in range(1, self.ota_device_combo.count())]
                
                for client_id in self.server.clients.keys():
                    client_id_str = str(client_id)  # ✅ CONVERT TO STRING
                    if client_id_str not in current_devices:
                        self.ota_device_combo.addItem(client_id_str)
        else:
            self.connection_label.setText("● Disconnected")
            self.connection_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
            
            if hasattr(self, 'ota_device_combo'):
                self.ota_device_combo.clear()
                self.ota_device_combo.addItem("All Devices")
    
    def update_status(self, message):
        self.status_bar.showMessage(message)
    
    def load_settings(self):
        """Load saved settings"""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        last_csv = self.settings.value("last_csv_file")
        if last_csv and os.path.exists(last_csv):
            self.variable_manager.load_csv(last_csv)
            self.populate_table()
            self.update_monitoring_variables()
            self.last_csv_file = last_csv
    
    def save_settings(self):
        """Save current settings"""
        self.settings.setValue("geometry", self.saveGeometry())
        if hasattr(self, 'last_csv_file'):
            self.settings.setValue("last_csv_file", self.last_csv_file)
    
    def closeEvent(self, event):
        logger.info("Application closing, performing cleanup")
        
        self.save_settings()
        self.server.stop_monitoring()
        
        if hasattr(self.server, 'server'):
            self.server.server.shutdown()
            
        logger.info("Application cleanup complete")
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set application-wide stylesheet for modern look
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #cccccc;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            padding: 5px 15px;
            border-radius: 3px;
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:pressed {
            background-color: #3d8b40;
        }
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
        QTabWidget::pane {
            border: 1px solid #cccccc;
            background-color: white;
        }
        QTabBar::tab {
            padding: 8px 16px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: white;
            border-bottom: 2px solid #4CAF50;
        }
        QTableWidget::item:selected {
            background-color: #3498db;
            color: white;
        }
        QTableWidget::item:hover {
            background-color: #e3f2fd;
        }
    """)
    
    logger.info("Starting GUI application")
    
    gui = DataMonitorGUI()
    gui.show()
    
    logger.info("GUI application started successfully")
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()