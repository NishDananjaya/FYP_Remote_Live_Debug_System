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

    def new_client(self, client, server):
        client_id = client['id']
        self.clients[client_id] = client
        print(f"New client connected (ID: {client_id}). Total clients: {len(self.clients)}")

    def client_left(self, client, server):
        client_id = client['id']
        if client_id in self.clients:
            del self.clients[client_id]
        print(f"Client disconnected (ID: {client_id}). Total clients: {len(self.clients)}")

    def message_received(self, client, server, message):
        try:
            self.process_message(client, message)
        except Exception as e:
            print(f"Error processing message: {e}")

    def process_message(self, client, message):
        # Use JSON handler to process the message
        result = self.json_handler.process_message(message)
        
        if result['type'] == 'response':
            print(f"Response received - ID: {result['command_id']}, Status: {result['status']}, Message: {result['message']}")
            
        elif result['type'] == 'data':
            print(f"Data received - Parameter: {result['parameter']}, Value: {result['value']}, Time: {time.strftime('%H:%M:%S', time.localtime(result['timestamp']))}")
            
            # Call GUI callback if available
            if hasattr(self, 'data_callback') and callable(self.data_callback):
                try:
                    self.data_callback(result['parameter'], result['value'], result['timestamp'])
                except Exception as e:
                    print(f"Error in data_callback: {e}")
                    
        elif result['type'] == 'error':
            print(f"JSON Error: {result['message']}")

    def start_monitoring(self):
        if self.monitoring_active:
            print("Monitoring is already active")
            return
        
        if not self.clients:
            print("No clients connected")
            return
        
        self.monitoring_active = True
        
        # Start monitoring in a separate thread
        self.monitoring_thread = threading.Thread(target=self.monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        print("Monitoring started")

    def stop_monitoring(self):
        if not self.monitoring_active:
            print("Monitoring is not active")
            return
        
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=2.0)
        
        print("Monitoring stopped")

    def monitoring_loop(self):
        print("Starting monitoring loop")
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
                
                # Wait before next iteration
                for _ in range(5):
                    if not self.monitoring_active:
                        break
                    time.sleep(0.1)
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
            self.monitoring_active = False

    def write_data(self, data_bytes=None):
        print("\nWRITE OPERATION SEQUENCE")
        
        if not self.clients:
            print("No clients connected")
            return
        
        # 1. First send SET_MTA
        set_mta_cmd = self.json_handler.create_set_mta_command(
            [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]
        )
        
        self.broadcast(set_mta_cmd)
        print("SET_MTA command sent")
        
        # Wait a bit for processing
        time.sleep(0.5)
        
        # 2. Get data to write if not provided
        if data_bytes is None:
            print("\nEnter 4 bytes to write (0-255), separated by space:")
            try:
                user_input = input(">> ").strip().split()
                if len(user_input) != 4:
                    raise ValueError("Please enter exactly 4 bytes.")
                    
                data_bytes = [int(b) & 0xFF for b in user_input]
            except ValueError as e:
                print(f"Invalid input: {e}")
                return
        
        # 3. Send DOWNLOAD command using JSON handler
        download_cmd = self.json_handler.create_download_command(data_bytes)
        
        self.broadcast(download_cmd)
        print(f"DOWNLOAD command sent with bytes: {data_bytes}")

    def broadcast(self, message):
        if self.clients and self.server:
            for client_id in list(self.clients.keys()):
                try:
                    self.server.send_message(self.clients[client_id], message)
                except Exception as e:
                    print(f"Error sending message to client {client_id}: {e}")
                    # Remove disconnected client
                    if client_id in self.clients:
                        del self.clients[client_id]

    def run_control_interface(self):
        while True:
            print("\nOptions:")
            print("1. Start monitoring")
            print("2. Stop monitoring")
            print("3. Write data")
            print("4. Exit")
            
            choice = input("Select an option: ").strip()
            
            if choice == '1':
                self.start_monitoring()
            elif choice == '2':
                self.stop_monitoring()
            elif choice == '3':
                self.write_data()
            elif choice == '4':
                break
            else:
                print("Invalid option")
                
            time.sleep(0.1)

    def write_data_gui(self, data_bytes):
        """Simplified write_data method for GUI to call (assumes data_bytes is provided)"""
        if not self.clients:
            print("No clients connected")
            return False
        
        try:
            # 1. First send SET_MTA
            set_mta_cmd = self.json_handler.create_set_mta_command(
                [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]
            )
            
            self.broadcast(set_mta_cmd)
            print("SET_MTA command sent")
            
            # Wait a bit for processing (non-blocking for GUI)
            time.sleep(0.5)
            
            # 2. Send DOWNLOAD command using JSON handler
            download_cmd = self.json_handler.create_download_command(data_bytes)
            
            self.broadcast(download_cmd)
            print(f"DOWNLOAD command sent with bytes: {data_bytes}")
            return True
            
        except Exception as e:
            print(f"Error in write_data_gui: {e}")
            return False

    def run(self):
        # Create WebSocket server
        self.server = WebsocketServer(host=self.host, port=self.port)
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)
        self.server.set_fn_message_received(self.message_received)
        
        print(f"Starting WebSocket server on {self.host}:{self.port}")
        
        # Start server in a separate thread
        server_thread = threading.Thread(target=self.server.run_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Run control interface in main thread
        self.run_control_interface()
        
        # Cleanup
        self.server.shutdown()
        print("Server stopped.")
        

if __name__ == "__main__":
    server = WebSocketServer()
    server.run()