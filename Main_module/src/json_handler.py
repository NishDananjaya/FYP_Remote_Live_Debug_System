import json
import time
from typing import Dict, Any, List, Optional
import os
import sys


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.append(project_root)

from src.logger_config import get_module_logger

class JSONHandler:
    """Handler for JSON message processing with new protocol communication support."""
    
    # Protocol constants
    MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB
    DEFAULT_TIMEOUT = 5  # 5 seconds for response timeout
    RESPONSE_TIMEOUT = 5  # Wait time for response
    
    # Message type constants
    MSG_TYPE_RESPONSE = 'response'
    MSG_TYPE_DATA = 'data'
    MSG_TYPE_COMMAND = 'command'
    MSG_TYPE_ERROR = 'error'

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize JSONHandler with optional configuration."""
        self.config = config or {}
        self.max_message_size = self.config.get('max_message_size', self.MAX_MESSAGE_SIZE)
        self.response_timeout = self.config.get('response_timeout', self.RESPONSE_TIMEOUT)
        self.logger = get_module_logger("JSONHandler")
        self.pending_responses = {}  # Track pending responses
        self.connection_id = "01"  # Default connection ID
        self.logger.debug(f"JSONHandler initialized with new protocol")

    def validate_message_size(self, message: str) -> bool:
        """Validate message size before processing."""
        message_size = len(message.encode('utf-8'))
        if message_size > self.max_message_size:
            self.logger.error(f"Message size {message_size} exceeds limit {self.max_message_size}")
            return False
        return True

    def process_message(self, message: str) -> Dict[str, Any]:
        """Process incoming JSON messages with new protocol."""
        start_time = time.time()
        
        try:
            if not isinstance(message, str) or not message.strip():
                return {'type': self.MSG_TYPE_ERROR, 'message': 'Invalid message'}
            
            if not self.validate_message_size(message):
                return {'type': self.MSG_TYPE_ERROR, 'message': 'Message too large'}

            self.logger.debug(f"Processing message: {message}")
            
            # Parse JSON
            data = json.loads(message)
            
            if not isinstance(data, dict):
                return {'type': self.MSG_TYPE_ERROR, 'message': 'Expected JSON object'}
            
            # Check if it's a response
            if 'res' in data:
                return self._process_response(data)
            else:
                return {'type': 'unknown', 'raw_data': data}
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON: {e}")
            return {'type': self.MSG_TYPE_ERROR, 'message': f'Invalid JSON: {e}'}
        except Exception as e:
            self.logger.exception(f"Error processing message: {e}")
            return {'type': self.MSG_TYPE_ERROR, 'message': str(e)}

    def _process_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process response messages from client."""
        res_type = data.get('res', '')
        self.logger.debug(f"Processing response type: {res_type}")
        
        if res_type == 'init':
            return {
                'type': self.MSG_TYPE_RESPONSE,
                'command': 'init',
                'con_id': data.get('con_id', ''),
                'status': 'success'
            }
        
        elif res_type == 'mem_read':
            address = data.get('add', '')
            value_str = data.get('value', '0b0')
            
            # Convert binary string to decimal value
            try:
                if value_str.startswith('0b'):
                    value = int(value_str, 2)
                elif value_str.startswith('0x'):
                    value = int(value_str, 16)
                else:
                    value = float(value_str)
            except (ValueError, TypeError):
                self.logger.warning(f"Could not convert value '{value_str}', using 0")
                value = 0.0
            
            return {
                'type': self.MSG_TYPE_DATA,
                'command': 'mem_read',
                'address': address,
                'value': value,
                'timestamp': time.time(),
                'status': 'success'
            }
        
        elif res_type == 'mem_write':
            return {
                'type': self.MSG_TYPE_RESPONSE,
                'command': 'mem_write',
                'address': data.get('add', ''),
                'state': data.get('state', 'unknown'),
                'status': 'success' if data.get('state') == 'success' else 'failed'
            }
        
        elif res_type == 'end':
            return {
                'type': self.MSG_TYPE_RESPONSE,
                'command': 'end',
                'con_id': data.get('con_id', ''),
                'status': 'success'
            }
        
        else:
            return {'type': 'unknown', 'raw_data': data}

    # NEW PROTOCOL COMMAND METHODS
    
    def create_init_command(self, con_id: str = "01") -> str:
        """Create initialization command."""
        self.connection_id = con_id
        command = {
            "cmd": "init",
            "con_id": con_id
        }
        json_cmd = json.dumps(command)
        self.logger.debug(f"Created init command: {json_cmd}")
        return json_cmd
    
    def create_mem_read_command(self, address: str, size: str = "08") -> str:
        """Create memory read command."""
        # Ensure address is in hex format
        if not address.startswith('0x'):
            address = f"0x{address}"
        
        command = {
            "cmd": "mem_read",
            "add": address,
            "size": size
        }
        json_cmd = json.dumps(command)
        self.logger.debug(f"Created mem_read command: {json_cmd}")
        return json_cmd
    
    def create_mem_write_command(self, address: str, size: str, data: Any, data_type: str = 'uint32_t') -> str:
        """Create memory write command with proper binary conversion."""
        # Ensure address is in hex format
        if not address.startswith('0x'):
            address = f"0x{address}"
        
        # Convert user input (int/float) to binary string based on data type
        data_binary = self.convert_to_binary(data, data_type, size)
        
        command = {
            "cmd": "mem_write",
            "add": address,
            "size": size,
            "data": data_binary  # Now properly formatted as "0bXXXXXXXX"
        }
        json_cmd = json.dumps(command)
        self.logger.debug(f"Created mem_write command: {json_cmd}")
        return json_cmd
    
    def convert_to_binary(self, value: Any, data_type: str, size: str) -> str:
        """Convert integer/float to binary string with proper bit width."""
        import struct
        
        try:
            # Determine bit width from size string
            bit_width = int(size)  # "08" -> 8, "16" -> 16, "32" -> 32
            
            # Convert based on data type
            if data_type in ['uint8_t', 'uint16_t', 'uint32_t']:
                # Unsigned integers
                int_value = int(abs(value))
                max_value = (2 ** bit_width) - 1
                
                # Clamp to valid range
                if int_value > max_value:
                    self.logger.warning(f"Value {int_value} exceeds max {max_value}, clamping")
                    int_value = max_value
                
                # Convert to binary with proper padding
                binary_str = bin(int_value)  # "0b1010"
                
            elif data_type in ['int8_t', 'int16_t', 'int32_t']:
                # Signed integers (two's complement)
                int_value = int(value)
                max_value = (2 ** (bit_width - 1)) - 1
                min_value = -(2 ** (bit_width - 1))
                
                # Clamp to valid range
                if int_value > max_value:
                    int_value = max_value
                elif int_value < min_value:
                    int_value = min_value
                
                # Convert to two's complement binary
                if int_value >= 0:
                    binary_str = bin(int_value)
                else:
                    # Two's complement for negative numbers
                    binary_str = bin((1 << bit_width) + int_value)
                    
            elif data_type == 'float':
                # IEEE 754 single precision (32-bit)
                float_value = float(value)
                bytes_data = struct.pack('<f', float_value)  # Little-endian float
                int_repr = int.from_bytes(bytes_data, byteorder='little')
                binary_str = bin(int_repr)
                
            elif data_type == 'double':
                # IEEE 754 double precision (64-bit)
                float_value = float(value)
                bytes_data = struct.pack('<d', float_value)  # Little-endian double
                int_repr = int.from_bytes(bytes_data, byteorder='little')
                binary_str = bin(int_repr)
            else:
                # Default fallback
                int_value = int(value)
                binary_str = bin(int_value)
            
            # Ensure binary string has "0b" prefix and proper padding
            if not binary_str.startswith('0b'):
                binary_str = '0b' + binary_str
            
            # Pad with zeros to match bit width (remove '0b', pad, add back)
            binary_digits = binary_str[2:]  # Remove '0b'
            padded_binary = binary_digits.zfill(bit_width)  # Pad to bit_width
            final_binary = '0b' + padded_binary
            
            self.logger.debug(f"Converted {value} ({data_type}) to {final_binary}")
            return final_binary
            
        except Exception as e:
            self.logger.error(f"Error converting {value} to binary: {e}")
            # Fallback to simple conversion
            return bin(int(value))
    
    def create_end_command(self, con_id: str = None) -> str:
        """Create end/termination command."""
        if con_id is None:
            con_id = self.connection_id
        
        command = {
            "cmd": "end",
            "con_id": con_id
        }
        json_cmd = json.dumps(command)
        self.logger.debug(f"Created end command: {json_cmd}")
        return json_cmd

    def get_data_size_from_type(self, data_type: str) -> str:
        """Get size string based on data type with flexible matching."""
        # Clean up the data type string
        data_type_clean = data_type.strip().lower().replace(' ', '').replace('_', '')
        
        # Comprehensive size mapping with multiple possible formats
        size_map = {
            # 8-bit types
            'uint8': '08',
            'uint8t': '08',
            'int8': '08',
            'int8t': '08',
            'char': '08',
            'byte': '08',
            'bool': '08',
            
            # 16-bit types
            'uint16': '16',
            'uint16t': '16',
            'int16': '16',
            'int16t': '16',
            'short': '16',
            'word': '16',
            
            # 32-bit types
            'uint32': '32',
            'uint32t': '32',
            'int32': '32',
            'int32t': '32',
            'long': '32',
            'dword': '32',
            'float': '32',
            'float32': '32',
            
            # 64-bit types
            'uint64': '64',
            'uint64t': '64',
            'int64': '64',
            'int64t': '64',
            'double': '64',
            'float64': '64',
            'longlong': '64'
        }
        
        # Try to find matching size
        size = size_map.get(data_type_clean)
        
        if size:
            self.logger.debug(f"Mapped data type '{data_type}' to size '{size}'")
            return size
        
        # If no exact match, try to extract bit size from the type name
        import re
        match = re.search(r'(\d+)', data_type)
        if match:
            bit_size = match.group(1)
            if bit_size in ['8', '16', '32', '64']:
                if len(bit_size) == 1:
                    bit_size = '0' + bit_size  # Pad single digit
                self.logger.debug(f"Extracted size '{bit_size}' from data type '{data_type}'")
                return bit_size
        
        # Log warning for unknown type
        self.logger.warning(f"Unknown data type '{data_type}', defaulting to 32-bit")
        return '32'  # Default to 32-bit instead of 8-bit for safety

    def get_handler_stats(self) -> Dict[str, Any]:
        """Get statistics about handler performance."""
        return {
            "max_message_size": self.max_message_size,
            "response_timeout": self.response_timeout,
            "connection_id": self.connection_id,
            "pending_responses": len(self.pending_responses)
        }