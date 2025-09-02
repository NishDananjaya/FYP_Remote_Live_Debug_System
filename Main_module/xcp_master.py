import json
from websocket_server import WebsocketServer
from datetime import datetime
import threading
import logging
import time

class XcpMaster:
    def __init__(self, port=8000):
        self.server = WebsocketServer(port=port, host='0.0.0.0', loglevel=logging.INFO)
        self.server.set_fn_new_client(self._on_connect)
        self.server.set_fn_client_left(self._on_disconnect)
        self.server.set_fn_message_received(self._on_message)
        self.clients = []
        self.response_handler = None

    def set_response_handler(self, handler):
        self.response_handler = handler

    def _on_connect(self, client, server):
        print(f"Gateway connected: {client['id']}")
        self.clients.append(client)
        
    def _on_disconnect(self, client, server):
        print(f"Gateway disconnected: {client['id']}")
        if client in self.clients:
            self.clients.remove(client)
            
    def _on_message(self, client, server, message):
        try:
            print("\n" + "="*60)
            print("RECEIVED FROM GATEWAY")
            print("="*60)
            print(message)
            print("="*60)
            
            data = json.loads(message)
            
            # Call the response handler if set
            if self.response_handler and data.get('type') == 'response':
                self.response_handler(data)
                
            if data.get('type') == 'response':
                print("\nXCP SLAVE RESPONSE:")
                print(f"Command: {data.get('command_name')}")
                print(f"Status: {data.get('status')}")
                print(f"Data: {[hex(x) for x in data.get('response_bytes', [])]}")
                
        except Exception as e:
            print(f"Error processing message: {e}")
            
    def send_command(self, command):
        if not self.clients:
            print("No gateway connected!")
            return False
            
        # Print command being sent
        print("\n" + "="*60)
        print("SENDING TO GATEWAY")
        print("="*60)
        print(json.dumps(command, indent=2))
        
        self.server.send_message(self.clients[0], json.dumps(command))
        return True
        
    def start(self):
        print(f"Starting XCP Master on port {self.server.port}")
        self.server.run_forever()

class XcpInteractiveConsole:
    def __init__(self, master):
        self.master = master
        self.commands = {
            '1': {"name": "CONNECT", "bytes": [0xFF] + [0x00]*7},
            '2': {"name": "DISCONNECT", "bytes": [0xFE] + [0x00]*7},
            '3': {"name": "SET_MTA", "bytes": [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]},
            '4': {"name": "UPLOAD", "bytes": [0xF5, 0x04] + [0x00]*6},
            '5': {"name": "WRITE", "bytes": None}  # Special handling
        }
        
    def _print_menu(self):
        print("\n" + "="*60)
        print("XCP COMMAND MENU".center(60))
        print("="*60)
        print("1. CONNECT")
        print("2. DISCONNECT")
        print("3. SET_MTA (to 0x20000028)")
        print("4. UPLOAD (4 bytes)")
        print("5. WRITE (Set MTA + Download)")
        print("6. Exit")
        print("="*60)
        
    def _handle_write(self):
        print("\nWRITE OPERATION SEQUENCE")
        
        # Create an event to wait for acknowledgment
        ack_received = threading.Event()
        ack_status = None
        
        # Callback to handle responses
        def response_handler(response):
            nonlocal ack_status
            if response.get('command_id', '').startswith('setmta_'):
                ack_status = response.get('status') == 'SUCCESS'
                print(f"\nSET_MTA Response: {'SUCCESS' if ack_status else 'FAILURE'}")
                ack_received.set()
        
        # Register the callback
        self.master.set_response_handler(response_handler)
        
        # 1. First send SET_MTA
        set_mta_cmd = {
            "type": "command",
            "command_id": f"setmta_{int(time.time())}",
            "command": {
                "name": "SET_MTA",
                "bytes": [0xF6, 0x00, 0x00, 0x00, 0x28, 0x00, 0x00, 0x20]
            }
        }
        
        if not self.master.send_command(set_mta_cmd):
            print("Failed to send SET_MTA command")
            return
        
        # Wait for acknowledgment with timeout
        print("Waiting for SET_MTA acknowledgment...")
        if not ack_received.wait(timeout=5):  # 5 second timeout
            print("Timeout waiting for SET_MTA acknowledgment")
            return
        
        if not ack_status:
            print("SET_MTA failed, aborting write operation")
            return
        
        # 2. Get data to write
        print("\nEnter 4 bytes to write (0-255), separated by space:")
        try:
            user_input = input(">> ").strip().split()
            if len(user_input) != 4:
                raise ValueError("Please enter exactly 4 bytes.")
                
            data_bytes = [int(b) & 0xFF for b in user_input]
            
            # 3. Send DOWNLOAD command
            download_cmd = {
                "type": "command",
                "command_id": f"download_{int(time.time())}",
                "command": {
                    "name": "DOWNLOAD",
                    "bytes": [0xF0, 0x04] + data_bytes + [0x00]*2
                }
            }
            self.master.send_command(download_cmd)
            
        except ValueError as ve:
            print(f"Input error: {ve}")
        finally:
            # Clean up the handler
            self.master.set_response_handler(None)
        
    def start(self):
        # Start server in background thread
        server_thread = threading.Thread(target=self.master.start)
        server_thread.daemon = True
        server_thread.start()
        
        # Wait for server to start
        time.sleep(1)
        
        while True:
            try:
                self._print_menu()
                choice = input("Enter command (1-6): ").strip()
                
                if choice == '6':
                    print("Exiting...")
                    break
                elif choice == '5':
                    self._handle_write()
                elif choice in self.commands:
                    cmd = {
                        "type": "command",
                        "command_id": f"{self.commands[choice]['name'].lower()}_{int(time.time())}",
                        "command": {
                            "name": self.commands[choice]["name"],
                            "bytes": self.commands[choice]["bytes"]
                        }
                    }
                    self.master.send_command(cmd)
                else:
                    print("Invalid choice. Please enter 1-6")
                    
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    master = XcpMaster(port=8000)
    console = XcpInteractiveConsole(master)
    console.start()
