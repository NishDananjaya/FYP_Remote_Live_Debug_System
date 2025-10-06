import os
import time
import threading
from websocket_server import WebsocketServer
from concurrent.futures import ThreadPoolExecutor
import sys
from queue import Queue, Empty
import uuid
from typing import Optional, Dict


# Add current directory to path to find json_handler
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.append(project_root)

from src.json_handler import JSONHandler
from src.logger_config import get_module_logger

# Get logger for this module
logger = get_module_logger("WebSocketServer")

class WebSocketServer:
    def __init__(self, host='0.0.0.0', port=8000):
        self.host = host
        self.port = port
        self.clients = {}
        self.monitoring_active = False
        self.monitoring_thread = None
        self.server = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.json_handler = JSONHandler()
        self.variable_manager = None
        
        # NEW: Protocol state management
        self.is_initialized = False
        self.response_queue = Queue()
        self.pending_responses = {}
        self.connection_id = "01"
        
        logger.info(f"WebSocketServer initialized on {host}:{port}")

    def new_client(self, client, server):
        client_id = client['id']
        self.clients[client_id] = client
        logger.info(f"New client connected (ID: {client_id}). Total clients: {len(self.clients)}")

    def client_left(self, client, server):
        client_id = client['id']
        if client_id in self.clients:
            del self.clients[client_id]
        logger.info(f"Client disconnected (ID: {client_id}). Total clients: {len(self.clients)}")

    def message_received(self, client, server, message):
        try:
            logger.debug(f"Message received from client {client['id']}: {message}")
            self.process_message(client, message)
        except Exception as e:
            logger.error(f"Error processing message from client {client['id']}: {e}")
            logger.exception("Full exception details:")

    def process_message(self, client, message):
        """Process message with new protocol."""
        result = self.json_handler.process_message(message)
        
        if result['type'] == 'response':
            logger.info(f"Response received - Command: {result.get('command')}, Status: {result.get('status')}")
            
            # Put response in queue for waiting threads
            self.response_queue.put(result)
            
            # Handle init response
            if result.get('command') == 'init' and result.get('status') == 'success':
                self.is_initialized = True
                logger.info("Debug mode initialized successfully")
            
            # Handle end response
            elif result.get('command') == 'end':
                self.is_initialized = False
                logger.info("Debug mode ended")
                
        elif result['type'] == 'data':
            logger.info(f"Data received - Address: {result.get('address')}, Value: {result.get('value')}")
            
            # Put in response queue
            self.response_queue.put(result)
            
            # Call GUI callback if available
            if hasattr(self, 'data_callback') and callable(self.data_callback):
                try:
                    # Determine parameter name from address
                    address = result.get('address', '')
                    value = result.get('value', 0)
                    timestamp = result.get('timestamp', time.time())
                    
                    # Find parameter name by matching address
                    param_name = self.find_parameter_by_address(address)
                    
                    # ADD THIS DEBUG LINE:
                    logger.info(f"Mapped address {address} to parameter '{param_name}'")
                    
                    self.data_callback(param_name, value, timestamp)
                except Exception as e:
                    logger.error(f"Error in data_callback: {e}")
                    
        elif result['type'] == 'error':
            logger.error(f"Protocol Error: {result.get('message')}")
    

    def find_parameter_by_address(self, address: str) -> str:
        """Find parameter name by address with flexible matching."""
        if not self.variable_manager:
            return address
        
        try:
            # Convert incoming address to integer for comparison
            if isinstance(address, str):
                if address.startswith('0x') or address.startswith('0X'):
                    target_addr = int(address, 16)
                else:
                    target_addr = int(address, 16) if 'x' in address.lower() else int(address)
            else:
                target_addr = int(address)
            
            # Search through all variables and their elements
            for var in self.variable_manager.variables:
                base_address = int(var['address'], 16)
                
                # Calculate addresses for all elements
                addresses = self.variable_manager.get_element_addresses(
                    var['address'], var['elements'], var['data_type']
                )
                
                # Check each element's address
                for i, element_addr in enumerate(addresses):
                    if element_addr == target_addr:
                        if var['elements'] > 1:
                            return f"{var['name']}[{i}]"
                        else:
                            return var['name']
            
            # If no exact match found, try fuzzy matching (within range)
            for var in self.variable_manager.variables:
                base_address = int(var['address'], 16)
                size_map = {
                    'uint8_t': 1, 'int8_t': 1,
                    'uint16_t': 2, 'int16_t': 2,
                    'uint32_t': 4, 'int32_t': 4,
                    'float': 4, 'double': 8
                }
                element_size = size_map.get(var['data_type'], 1)
                max_address = base_address + (var['elements'] * element_size)
                
                if base_address <= target_addr < max_address:
                    # Calculate which element this is
                    element_index = (target_addr - base_address) // element_size
                    if element_index < var['elements']:
                        if var['elements'] > 1:
                            return f"{var['name']}[{element_index}]"
                        else:
                            return var['name']
            
            return f"Unknown_0x{target_addr:08X}"
            
        except Exception as e:
            logger.error(f"Error finding parameter for address {address}: {e}")
            return address

    def send_init_command(self) -> bool:
        """Send initialization command and wait for response."""
        if not self.clients:
            logger.error("No clients connected")
            return False
        
        logger.info("Sending init command...")
        init_cmd = self.json_handler.create_init_command(self.connection_id)
        self.broadcast(init_cmd)
        
        # Wait for response
        response = self.wait_for_response('init', timeout=5)
        if response and response.get('status') == 'success':
            self.is_initialized = True
            logger.info("Initialization successful")
            return True
        else:
            logger.error("Initialization failed or timed out")
            return False

    def send_end_command(self) -> bool:
        """Send end command and wait for response."""
        if not self.clients:
            logger.error("No clients connected")
            return False
        
        logger.info("Sending end command...")
        end_cmd = self.json_handler.create_end_command(self.connection_id)
        self.broadcast(end_cmd)
        
        # Wait for response
        response = self.wait_for_response('end', timeout=5)
        if response and response.get('status') == 'success':
            self.is_initialized = False
            logger.info("Session ended successfully")
            return True
        else:
            logger.error("End command failed or timed out")
            return False

    def wait_for_response(self, command_type: str, timeout: float = 5.0) -> Optional[Dict]:
        """Wait for a specific response with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = self.response_queue.get(timeout=0.1)
                
                # Check if this is the response we're waiting for
                if response.get('command') == command_type or response.get('type') == 'data':
                    return response
                else:
                    # Put it back if it's not what we're looking for
                    self.response_queue.put(response)
                    time.sleep(0.1)
                    
            except Empty:
                continue
        
        logger.warning(f"Timeout waiting for {command_type} response")
        return None


    def start_dynamic_monitoring(self, variable_manager):
        """Start monitoring with dynamic variables from CSV."""
        if self.monitoring_active:
            logger.warning("Monitoring is already active, stopping it first...")
            self.stop_monitoring()
            time.sleep(0.5)
        
        if not self.clients:
            logger.warning("No clients connected, cannot start monitoring")
            return False
        
        # Initialize debug mode first
        if not self.is_initialized:
            if not self.send_init_command():
                logger.error("Failed to initialize debug mode")
                return False
        
        self.variable_manager = variable_manager
        self.monitoring_active = True
        self.monitoring_thread = None
        
        # Start monitoring in a new thread
        self.monitoring_thread = threading.Thread(target=self.dynamic_monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
        logger.info("Dynamic monitoring started successfully")
        return True

    def stop_monitoring(self):
        """Stop monitoring."""
        if not self.monitoring_active:
            logger.warning("Monitoring is not active")
            return False
        
        logger.info("Stopping monitoring...")
        self.monitoring_active = False
        
        # Wait for thread to finish
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=3.0)
            
            if self.monitoring_thread.is_alive():
                logger.warning("Monitoring thread did not stop cleanly")
            else:
                logger.info("Monitoring thread stopped cleanly")
        
        self.monitoring_thread = None
        
        # Send end command
        if self.is_initialized:
            self.send_end_command()
        
        logger.info("Monitoring stopped successfully")
        return True

    def dynamic_monitoring_loop(self):
        """Monitoring loop with new protocol and proper size handling"""
        logger.info("Starting dynamic monitoring loop with new protocol")
        
        if not self.variable_manager:
            logger.error("No variable manager available")
            self.monitoring_active = False
            return
        
        try:
            while self.monitoring_active:
                if not self.clients:
                    logger.debug("No clients connected, waiting...")
                    time.sleep(0.5)
                    continue
                
                # Iterate through all variables
                for var in self.variable_manager.variables:
                    if not self.monitoring_active:
                        logger.info("Monitoring stopped, exiting loop")
                        break
                    
                    # Get variable details
                    var_name = var['name']
                    data_type = var['data_type']
                    base_address = int(var['address'], 16)
                    num_elements = var['elements']
                    
                    # Get data size based on type - WITH LOGGING
                    data_size = self.json_handler.get_data_size_from_type(data_type)
                    logger.debug(f"Variable '{var_name}' type '{data_type}' mapped to size '{data_size}' bits")
                    
                    # Calculate element size in bytes for address calculation
                    byte_size_map = {
                        '08': 1,
                        '16': 2,
                        '32': 4,
                        '64': 8
                    }
                    element_byte_size = byte_size_map.get(data_size, 4)
                    
                    # Read each element with correct address spacing
                    for i in range(num_elements):
                        if not self.monitoring_active:
                            break
                        
                        # Calculate address for this element
                        element_address = base_address + (i * element_byte_size)
                        addr_hex = f"0x{element_address:08X}"
                        
                        # Create parameter name
                        if num_elements > 1:
                            param_name = f"{var_name}[{i}]"
                        else:
                            param_name = var_name
                        
                        # Send mem_read command with CORRECT SIZE
                        read_cmd = self.json_handler.create_mem_read_command(addr_hex, data_size)
                        self.broadcast(read_cmd)
                        logger.debug(f"Sent: {read_cmd}")  # Log the actual command
                        
                        # Wait for response
                        response = self.wait_for_response('mem_read', timeout=5.0)
                        
                        if response and response.get('type') == 'data':
                            logger.debug(f"Received data for {param_name}: {response.get('value')}")
                        else:
                            logger.warning(f"No response for {param_name} at {addr_hex}")
                        
                        time.sleep(0.005)
                
                if not self.monitoring_active:
                    break
                
                logger.debug("Monitoring cycle completed")
                
                # Wait before next cycle
                for _ in range(10):
                    if not self.monitoring_active:
                        break
                    time.sleep(0.005)
                    
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            logger.exception("Full exception details:")
        finally:
            self.monitoring_active = False
            logger.info("Monitoring loop exited")


    def write_data_with_address(self, address, data_value, data_type='uint32_t'):
        """Write data to a specific address with new protocol."""
        logger.info(f"Writing data to address 0x{address:08X}, value: {data_value}, type: {data_type}")
        
        if not self.clients:
            logger.error("No clients connected, cannot write data")
            return False
        
        if not self.is_initialized:
            logger.warning("Debug mode not initialized, initializing now...")
            if not self.send_init_command():
                return False
        
        try:
            # Format address as hex string
            addr_hex = f"0x{address:08X}"
            
            # Get data size based on type (from CSV)
            data_size = self.json_handler.get_data_size_from_type(data_type)
            
            # Create and send mem_write command WITH data_type for proper conversion
            write_cmd = self.json_handler.create_mem_write_command(
                addr_hex, 
                data_size, 
                data_value, 
                data_type  # PASS THE DATA TYPE!
            )
            self.broadcast(write_cmd)
            logger.info(f"Sent write command to {addr_hex} with size {data_size} bits")
            
            # Wait for response
            response = self.wait_for_response('mem_write', timeout=5.0)
            
            if response and response.get('status') == 'success':
                logger.info(f"Write successful to {addr_hex}")
                return True
            else:
                logger.error(f"Write failed or timed out for {addr_hex}")
                return False
                
        except Exception as e:
            logger.error(f"Error in write_data_with_address: {e}")
            logger.exception("Full traceback:")
            return False

    def broadcast(self, message):
        """Broadcast message to all connected clients"""
        if self.clients and self.server:
            for client_id in list(self.clients.keys()):
                try:
                    self.server.send_message(self.clients[client_id], message)
                    logger.debug(f"Message sent to client {client_id}: {message}")
                except Exception as e:
                    logger.error(f"Error sending message to client {client_id}: {e}")
                    # Remove disconnected client
                    if client_id in self.clients:
                        del self.clients[client_id]
                        logger.info(f"Removed disconnected client {client_id}")

    def send_to_client(self, client_id: str, message: str):
        """Send message to specific client"""
        if client_id in self.clients and self.server:
            try:
                client = self.clients[client_id]
                self.server.send_message(client, message)
                logger.debug(f"Message sent to client {client_id}")
                return True
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
                return False
        return False

    def broadcast_ota(self, message: str, device_ids: list = None):
        """Broadcast OTA message to specific or all devices"""
        if device_ids:
            for device_id in device_ids:
                self.send_to_client(device_id, message)
        else:
            self.broadcast(message)

    def run_control_interface(self):
        """Run command-line control interface (for standalone mode)"""
        logger.info("Starting control interface")
        
        
        while True:
            # print("\nOptions:")
            # print("1. Show connected clients")
            # print("2. Exit")
            
            choice = input("Select an option: ").strip()
            logger.info(f"User selected option: {choice}")
            
            if choice == '1':
                if self.clients:
                    print(f"\nConnected clients: {len(self.clients)}")
                    for client_id in self.clients:
                        print(f"  - Client ID: {client_id}")
                else:
                    print("No clients connected")
            elif choice == '2':
                logger.info("Exiting control interface")
                break
            else:
                logger.warning(f"Invalid option selected: {choice}")
                print("Invalid option")
                
            time.sleep(0.1)

    def run(self):
        """Start the WebSocket server"""
        # Create WebSocket server
        self.server = WebsocketServer(host=self.host, port=self.port)
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)
        self.server.set_fn_message_received(self.message_received)
        
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        print(f"Starting WebSocket server on {self.host}:{self.port}")
        
        # Start server in a separate thread
        server_thread = threading.Thread(target=self.server.run_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Run control interface in main thread (only if running standalone)
        if __name__ == "__main__":
            self.run_control_interface()
            
            # Cleanup
            self.server.shutdown()
            logger.info("Server stopped.")
            print("Server stopped.")

if __name__ == "__main__":
    server = WebSocketServer()
    server.run()
