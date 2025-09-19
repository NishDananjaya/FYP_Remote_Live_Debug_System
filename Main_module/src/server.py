import os
import time
import threading
from websocket_server import WebsocketServer
from concurrent.futures import ThreadPoolExecutor
import sys

# Add current directory to path to find json_handler
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from json_handler import JSONHandler
from logger_config import get_module_logger

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
        # Use JSON handler to process the message
        result = self.json_handler.process_message(message)
        
        if result['type'] == 'response':
            logger.info(f"Response received - ID: {result['command_id']}, Status: {result['status']}, Message: {result['message']}")
            
        elif result['type'] == 'data':
            logger.info(f"Data received - Parameter: {result['parameter']}, Value: {result['value']}, Time: {time.strftime('%H:%M:%S', time.localtime(result['timestamp']))}")
            
            # Call GUI callback if available
            if hasattr(self, 'data_callback') and callable(self.data_callback):
                try:
                    self.data_callback(result['parameter'], result['value'], result['timestamp'])
                except Exception as e:
                    logger.error(f"Error in data_callback: {e}")
                    
        elif result['type'] == 'error':
            logger.error(f"JSON Error: {result['message']}")

    def start_monitoring(self):
        if self.monitoring_active:
            logger.warning("Monitoring is already active")
            return
        
        if not self.clients:
            logger.warning("No clients connected, cannot start monitoring")
            return
        
        self.monitoring_active = True
        
        # Start monitoring in a separate thread
        self.monitoring_thread = threading.Thread(target=self.monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        logger.info("Monitoring started")

    def stop_monitoring(self):
        if not self.monitoring_active:
            logger.warning("Monitoring is not active")
            return
        
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=2.0)
        
        logger.info("Monitoring stopped")

    def monitoring_loop(self):
        logger.info("Starting monitoring loop")
        try:
            while True:
                if not self.monitoring_active:
                    break
                if not self.clients:
                    time.sleep(0.1)
                    continue
                
                # Use JSON handler to create commands
                set_mta_cmd = self.json_handler.create_set_mta_command(
                    [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]
                )
                upload_voltage_cmd = self.json_handler.create_upload_command("voltage")
                upload_current_cmd = self.json_handler.create_upload_command("current")
                upload_ports_cmd = self.json_handler.create_upload_command("ports")
                
                # Send all commands to all connected clients
                self.broadcast(set_mta_cmd)
                time.sleep(0.1)
                self.broadcast(upload_voltage_cmd)
                time.sleep(0.1)
                self.broadcast(upload_current_cmd)
                time.sleep(0.1)
                self.broadcast(upload_ports_cmd)
                
                logger.debug("Monitoring cycle completed")
                
                # Wait before next iteration
                for _ in range(5):
                    if not self.monitoring_active:
                        break
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            logger.exception("Full exception details:")
            self.monitoring_active = False

    def write_data(self, data_bytes=None):
        logger.info("Starting WRITE OPERATION SEQUENCE")
        
        if not self.clients:
            logger.error("No clients connected, cannot write data")
            return
        
        # 1. First send SET_MTA
        set_mta_cmd = self.json_handler.create_set_mta_command(
            [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]
        )
        
        self.broadcast(set_mta_cmd)
        logger.info("SET_MTA command sent")
        
        # Wait a bit for processing
        time.sleep(0.5)
        
        # 2. Get data to write if not provided
        if data_bytes is None:
            logger.info("Prompting user for data bytes")
            print("\nEnter 4 bytes to write (0-255), separated by space:")
            try:
                user_input = input(">> ").strip().split()
                if len(user_input) != 4:
                    raise ValueError("Please enter exactly 4 bytes.")
                    
                data_bytes = [int(b) & 0xFF for b in user_input]
                logger.info(f"User provided bytes: {data_bytes}")
            except ValueError as e:
                logger.error(f"Invalid input: {e}")
                return
        
        # 3. Send DOWNLOAD command using JSON handler
        download_cmd = self.json_handler.create_download_command(data_bytes)
        
        self.broadcast(download_cmd)
        logger.info(f"DOWNLOAD command sent with bytes: {data_bytes}")

    def broadcast(self, message):
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

    def run_control_interface(self):
        logger.info("Starting control interface")
        while True:
            print("\nOptions:")
            print("1. Start monitoring")
            print("2. Stop monitoring")
            print("3. Write data")
            print("4. Exit")
            
            choice = input("Select an option: ").strip()
            logger.info(f"User selected option: {choice}")
            
            if choice == '1':
                self.start_monitoring()
            elif choice == '2':
                self.stop_monitoring()
            elif choice == '3':
                self.write_data()
            elif choice == '4':
                logger.info("Exiting control interface")
                break
            else:
                logger.warning(f"Invalid option selected: {choice}")
                print("Invalid option")
                
            time.sleep(0.1)

    def write_data_gui(self, data_bytes):
        """Simplified write_data method for GUI to call (assumes data_bytes is provided)"""
        logger.info(f"GUI write operation requested with bytes: {data_bytes}")
        
        if not self.clients:
            logger.error("No clients connected, cannot write data")
            return False
        
        try:
            # 1. First send SET_MTA
            set_mta_cmd = self.json_handler.create_set_mta_command(
                [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]
            )
            
            self.broadcast(set_mta_cmd)
            logger.info("SET_MTA command sent")
            
            # Wait a bit for processing (non-blocking for GUI)
            time.sleep(0.5)
            
            # 2. Send DOWNLOAD command using JSON handler
            download_cmd = self.json_handler.create_download_command(data_bytes)
            
            self.broadcast(download_cmd)
            logger.info(f"DOWNLOAD command sent with bytes: {data_bytes}")
            return True
            
        except Exception as e:
            logger.error(f"Error in write_data_gui: {e}")
            logger.exception("Full exception details:")
            return False

    def run(self):
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
        
        # Run control interface in main thread
        self.run_control_interface()
        
        # Cleanup
        self.server.shutdown()
        logger.info("Server stopped.")
        print("Server stopped.")
        
if __name__ == "__main__":
    server = WebSocketServer()
    server.run()