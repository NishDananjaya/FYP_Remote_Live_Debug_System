import json
import websocket
import spidev
import time
import threading


class XcpSpiHandler:
    def __init__(self, bus=0, device=0, speed_hz=500000):
        self.spi = spidev.SpiDev()
        self.bus = bus
        self.device = device
        self.speed_hz = speed_hz
        self.connect()

    def connect(self):
        self.spi.open(self.bus, self.device)
        self.spi.max_speed_hz = self.speed_hz
        self.spi.mode = 0b00
        print("[SPI] Connected")

    def disconnect(self):
        self.spi.close()
        print("[SPI] Disconnected")

    def send_command(self, command):
        if len(command) < 8:
            command += [0x00] * (8 - len(command))

        print(f"[SPI] TX → {[hex(x) for x in command]}")
        self.spi.xfer2(command)
        time.sleep(0.001)

        dummy = [0xAA] * 8
        self.spi.xfer2(dummy)        
        response = self.spi.xfer2(dummy)

        print(f"[SPI] RX ← {[hex(x) for x in response]}")

        return response

    def send_set_mta(self, address):
    
        addr_high = (address >> 24) & 0xFF
        addr_low  = address & 0xFF
        set_mta_cmd = [0xF6, 0x00, 0x00, 0x00, addr_low, 0x00, 0x00, addr_high]

        print(f"[SPI] SET_MTA TX → {[hex(x) for x in set_mta_cmd]}")

        resp1=self.spi.xfer2(set_mta_cmd)
        print(f"{[hex(x) for x in resp1]}")
        time.sleep(0.001)
        dummy = [0xAA] * 8
        self.spi.xfer2(dummy)
        resp=self.spi.xfer2(dummy)
        
        # Print RX
        print(f"[SPI] SET_MTA RX ← {[hex(x) for x in resp]}")

        # Check response
        if resp[0] == 0xFF:
            print("[SPI] SET_MTA Success")
            return True
        elif resp[0] == 0xFE:
            print("[SPI] SET_MTA Error")
            return False
        else:
            print(f"[SPI] Unexpected SET_MTA response: {[hex(x) for x in resp]}")
            return False


class XcpGatewayClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.connected = False
        self.spi_handler = XcpSpiHandler()

    def on_open(self, ws):
        print(f"[WS] Connected to {self.ws_url}")
        self.connected = True

    def on_close(self, ws, close_status_code, close_msg):
        print("[WS] Disconnected from server")
        self.connected = False
        self.spi_handler.disconnect()

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages and perform SPI operations."""
        try:
            data = json.loads(message)
            cmd = data.get("cmd")

            if not cmd:
                print("[WS] No 'cmd' in message.")
                return

            # -----------------------------
            # INIT COMMAND
            # -----------------------------
            if cmd == "init":
                con_id = data.get("con_id", "00")
                ws.send(json.dumps({"res": "init", "con_id": con_id}))
                print(f"[WS] Init acknowledged (con_id={con_id})")

            # -----------------------------
            # MEMORY READ COMMAND
            # -----------------------------
            elif cmd == "mem_read":
                addr_str = data.get("add")
                size_str = data.get("size", "1")

                address = int(addr_str, 16)
                # Parse size as hex or decimal, then map to number of bytes
                size = int(size_str, 16) if "0x" in size_str else int(size_str)
                # Map bit size to number of bytes
                if size == 8:
                    num_elements = 1
                elif size == 16:
                    num_elements = 2
                elif size == 32:
                    num_elements = 4
                else:
                    num_elements = size  # Fallback for other sizes

                print(f"[WS] mem_read → addr={addr_str}, size={size}, num_elements={num_elements}")

                # Send SET_MTA once and check response
                if not self.spi_handler.send_set_mta(address):
                    ws.send(json.dumps({
                        "res": "mem_read",
                        "add": addr_str,
                        "value": None,
                        "error": "SET_MTA failed"
                    }))
                    return

                # Construct SPI SHORT_UPLOAD command (0xF5)
                addr_high = (address >> 24) & 0xFF
                addr_low = address & 0xFF
                spi_cmd = [0xF5, num_elements, 0x00, 0x00, addr_low, 0x00, 0x00, addr_high]
                spi_resp = self.spi_handler.send_command(spi_cmd)

                # Extract the requested number of bytes from response
                if spi_resp[0] == 0xFF:  # Check for successful response
                    # Add length checks for safety
                    if size == 8:
                        if len(spi_resp) < 2:
                            ws.send(json.dumps({
                                "res": "mem_read",
                                "add": addr_str,
                                "value": None,
                                "error": "Insufficient response length for 8-bit"
                            }))
                            print("[WS] Insufficient response length for 8-bit")
                            return
                        value = spi_resp[1]
                    elif size == 16:
                        if len(spi_resp) < 3:
                            ws.send(json.dumps({
                                "res": "mem_read",
                                "add": addr_str,
                                "value": None,
                                "error": "Insufficient response length for 16-bit"
                            }))
                            print("[WS] Insufficient response length for 16-bit")
                            return
                        value = (spi_resp[2] << 8) | spi_resp[1]  # Little-endian 16-bit
                    elif size == 32:
                        if len(spi_resp) < 5:
                            ws.send(json.dumps({
                                "res": "mem_read",
                                "add": addr_str,
                                "value": None,
                                "error": "Insufficient response length for 32-bit"
                            }))
                            print("[WS] Insufficient response length for 32-bit")
                            return
                        value = (spi_resp[4] << 24) | (spi_resp[3] << 16) | (spi_resp[2] << 8) | spi_resp[1]  # Little-endian 32-bit
                    else:
                        value = 0  # Fallback for unsupported sizes
                    # Format as binary string with correct bit-width
                    binary_value = f"0b{value:0{size}b}"
                    ws.send(json.dumps({
                        "res": "mem_read",
                        "add": addr_str,
                        "value": binary_value
                    }))
                    print(f"[WS] Sent mem_read response: {binary_value}")
                else:
                    ws.send(json.dumps({
                        "res": "mem_read",
                        "add": addr_str,
                        "value": None,
                        "error": "SHORT_UPLOAD failed"
                    }))
                    print(f"[WS] SHORT_UPLOAD failed: {[hex(x) for x in spi_resp]}")

            # -----------------------------
            # MEMORY WRITE COMMAND
            # -----------------------------
            elif cmd == "mem_write":
                addr_str = data.get("add")
                data_bits = data.get("data", "0b00000000")
                size_str = data.get("size", "1")

                address = int(addr_str, 16)
                size = int(size_str, 16) if "0x" in size_str else int(size_str)
                data_byte = int(data_bits, 2)

                print(f"[WS] mem_write → addr={addr_str}, data={data_bits}")

                # Send SET_MTA once and check response
                if not self.spi_handler.send_set_mta(address):
                    ws.send(json.dumps({
                        "res": "mem_write",
                        "add": addr_str,
                        "state": "SET_MTA failed"
                    }))
                    return

                # Construct SPI write command (example)
                spi_cmd = [0xF2, data_byte, size, 0x00, 0x00, 0x00, 0x00, 0x00]
                spi_resp = self.spi_handler.send_command(spi_cmd)

                write_status = "success" if spi_resp[0] == 0xFF else "fail"
                ws.send(json.dumps({
                    "res": "mem_write",
                    "add": addr_str,
                    "state": write_status
                }))
                print(f"[WS] Sent mem_write response: {write_status}")

            else:
                print(f"[WS] Unknown cmd: {cmd}")

        except Exception as e:
            print(f"[ERROR] Failed to process message: {e}")

    def connect(self):
        print(f"[WS] Connecting to {self.ws_url}...")
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_close=self.on_close,
            on_message=self.on_message
        )

        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()


if __name__ == "__main__":
    
    NGROK_WS_URL = "wss://divine-next-lionfish.ngrok-free.app"

    gateway = XcpGatewayClient(NGROK_WS_URL)
    gateway.connect()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SYS] Shutting down...")
        gateway.spi_handler.disconnect()