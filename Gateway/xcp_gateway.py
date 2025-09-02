import json
import websocket
import spidev
import time
from datetime import datetime
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
        print("SPI Connected")

    def disconnect(self):
        self.spi.close()
        print("SPI Disconnected")

    def send_xcp_command(self, command):
        if len(command) != 8:
            command = self._pad_command(command)

        # Print only once for clarity
        print(f"\n[SPI] Sending: {[hex(x) for x in command]}")

        # Send command
        self.spi.xfer2(command)
        time.sleep(0.01)

        # Get response
        dummy = [0xAA] * 8
        self.spi.xfer2(dummy)
        response = self.spi.xfer2(dummy)

        print(f"[SPI] Received: {[hex(x) for x in response]}")
        return response

    def _pad_command(self, command):
        return command + [0x00] * (8 - len(command))


class XcpGatewayClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.connected = False
        self.spi_handler = XcpSpiHandler()

    def on_open(self, ws):
        print(f"Connected to XCP Master at {self.ws_url}")
        self.connected = True

    def on_close(self, ws, close_status_code, close_msg):
        print("Disconnected from XCP Master")
        self.connected = False
        self.spi_handler.disconnect()

    def on_message(self, ws, message):
        try:
            data = json.loads(message)

            if data.get('type') == 'command':
                command = data.get('command', {}).get('bytes')
                if not command:
                    return

                # Send to XCP slave
                response = self.spi_handler.send_xcp_command(command)

                # Prepare response
                response_data = {
                    "type": "response",
                    "timestamp": datetime.utcnow().isoformat(),
                    "command_id": data.get('command_id'),
                    "command_name": data.get('command', {}).get('name', 'UNKNOWN'),
                    "response_bytes": response,
                    "status": "SUCCESS" if response and response[0] == 0xFF else "ERROR"
                }

                # Send back to master
                self.ws.send(json.dumps(response_data))

        except Exception as e:
            print(f"Error processing message: {e}")

    def connect(self):
        print(f"Connecting to {self.ws_url}...")
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
    # Replace with your ngrok WebSocket URL
    NGROK_WS_URL = "wss://divine-next-lionfish.ngrok-free.app"

    gateway = XcpGatewayClient(NGROK_WS_URL)
    gateway.connect()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        gateway.spi_handler.disconnect()
