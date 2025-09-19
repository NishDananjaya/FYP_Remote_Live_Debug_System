import json
import time

class JSONHandler:
    def __init__(self):
        pass
    
    def process_message(self, message):
        """Process incoming JSON messages and return parsed data"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'response':
                return self._process_response(data)
            elif message_type == 'data':
                return self._process_data(data)
            else:
                return {'type': 'unknown', 'raw_data': data}
                
        except json.JSONDecodeError:
            return {'type': 'error', 'message': f"Invalid JSON received: {message}"}
    
    def _process_response(self, data):
        """Process response messages"""
        command_id = data.get('command_id', '')
        status = data.get('status', '')
        message_text = data.get('message', '')
        
        return {
            'type': 'response',
            'command_id': command_id,
            'status': status,
            'message': message_text
        }
    
    def _process_data(self, data):
        """Process data messages"""
        parameter = data.get('parameter', '')
        value = data.get('value', '')
        timestamp = data.get('timestamp', '')
        
        # Convert value and timestamp to numbers
        try:
            value_num = float(value)
        except (ValueError, TypeError):
            value_num = 0.0
        
        try:
            timestamp_num = float(timestamp)
        except (ValueError, TypeError):
            timestamp_num = time.time()
        
        return {
            'type': 'data',
            'parameter': parameter,
            'value': value_num,
            'timestamp': timestamp_num
        }
    
    def create_command(self, command_name, command_id=None, bytes_data=None):
        """Create JSON command messages"""
        if command_id is None:
            command_id = f"{command_name.lower()}_{int(time.time())}"
        
        command = {
            "type": "command",
            "command_id": command_id,
            "command": {
                "name": command_name,
                "bytes": bytes_data or []
            }
        }
        
        return json.dumps(command)
    
    def create_set_mta_command(self, mta_bytes):
        """Create SET_MTA command"""
        return self.create_command("SET_MTA", f"setmta_{int(time.time())}", mta_bytes)
    
    def create_upload_command(self, parameter_type):
        """Create UPLOAD command for specific parameter"""
        command_id = f"upload_{parameter_type}_{int(time.time())}"
        # Default upload bytes - can be customized per parameter type
        upload_bytes = [0xF5, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        return self.create_command("UPLOAD", command_id, upload_bytes)
    
    def create_download_command(self, data_bytes):
        """Create DOWNLOAD command with data bytes"""
        # DOWNLOAD command format: [0xF0, 0x04] + 4 data bytes + [0x00]*2
        download_bytes = [0xF0, 0x04] + data_bytes + [0x00]*2
        return self.create_command("DOWNLOAD", f"download_{int(time.time())}", download_bytes)