import json
import time
from logger_config import get_module_logger

# Get logger for this module
logger = get_module_logger("JSONHandler")

class JSONHandler:
    def __init__(self):
        logger.debug("JSONHandler initialized")
    
    def process_message(self, message):
        """Process incoming JSON messages and return parsed data"""
        try:
            logger.debug(f"Processing message: {message}")
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'response':
                result = self._process_response(data)
                logger.info(f"Processed response: {result}")
                return result
            elif message_type == 'data':
                result = self._process_data(data)
                logger.info(f"Processed data: {result}")
                return result
            else:
                result = {'type': 'unknown', 'raw_data': data}
                logger.warning(f"Unknown message type: {message_type}, data: {data}")
                return result
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON received: {message}, error: {e}"
            logger.error(error_msg)
            return {'type': 'error', 'message': error_msg}
        except Exception as e:
            error_msg = f"Unexpected error processing message: {e}"
            logger.exception(error_msg)
            return {'type': 'error', 'message': error_msg}
    
    def _process_response(self, data):
        """Process response messages"""
        logger.debug(f"Processing response: {data}")
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
        logger.debug(f"Processing data: {data}")
        parameter = data.get('parameter', '')
        value = data.get('value', '')
        timestamp = data.get('timestamp', '')
        
        # Convert value and timestamp to numbers
        try:
            value_num = float(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert value '{value}' to float: {e}, using 0.0")
            value_num = 0.0
        
        try:
            timestamp_num = float(timestamp)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert timestamp '{timestamp}' to float: {e}, using current time")
            timestamp_num = time.time()
        
        result = {
            'type': 'data',
            'parameter': parameter,
            'value': value_num,
            'timestamp': timestamp_num
        }
        
        logger.debug(f"Processed data result: {result}")
        return result
    
    def create_command(self, command_name, command_id=None, bytes_data=None):
        """Create JSON command messages"""
        logger.debug(f"Creating command: {command_name}, id: {command_id}, bytes: {bytes_data}")
        
        if command_id is None:
            command_id = f"{command_name.lower()}_{int(time.time())}"
            logger.debug(f"Generated command_id: {command_id}")
        
        command = {
            "type": "command",
            "command_id": command_id,
            "command": {
                "name": command_name,
                "bytes": bytes_data or []
            }
        }
        
        json_command = json.dumps(command)
        logger.debug(f"Created command JSON: {json_command}")
        return json_command
    
    def create_set_mta_command(self, mta_bytes):
        """Create SET_MTA command"""
        logger.debug(f"Creating SET_MTA command with bytes: {mta_bytes}")
        return self.create_command("SET_MTA", f"setmta_{int(time.time())}", mta_bytes)
    
    def create_upload_command(self, parameter_type):
        """Create UPLOAD command for specific parameter"""
        logger.debug(f"Creating UPLOAD command for parameter: {parameter_type}")
        command_id = f"upload_{parameter_type}_{int(time.time())}"
        # Default upload bytes - can be customized per parameter type
        upload_bytes = [0xF5, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        return self.create_command("UPLOAD", command_id, upload_bytes)
    
    def create_download_command(self, data_bytes):
        """Create DOWNLOAD command with data bytes"""
        logger.debug(f"Creating DOWNLOAD command with data bytes: {data_bytes}")
        # DOWNLOAD command format: [0xF0, 0x04] + 4 data bytes + [0x00]*2
        download_bytes = [0xF0, 0x04] + data_bytes + [0x00]*2
        return self.create_command("DOWNLOAD", f"download_{int(time.time())}", download_bytes)