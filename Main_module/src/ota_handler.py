"""
OTA (Over-The-Air) Update Handler
Manages firmware update workflow for WebSocket connected devices
"""

import os
import json
import time
import hashlib
import threading
from pathlib import Path
from enum import Enum
from typing import Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass

from logger_config import get_module_logger

# Get logger for this module
logger = get_module_logger("OTAHandler")

class OTAStatus(Enum):
    """OTA Update Status States"""
    IDLE = "idle"
    VALIDATING = "validating"
    PREPARING = "preparing"
    TRANSFERRING = "transferring"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class FirmwareInfo:
    """Firmware file information"""
    file_path: str
    file_name: str
    file_size: int
    checksum: str
    version: str
    chunks: int
    chunk_size: int = 1024  # Default 1KB chunks

@dataclass
class DeviceInfo:
    """Device information for OTA update"""
    device_id: str
    current_version: str
    device_type: str
    connection_status: bool

class OTAHandler:
    """
    Handles OTA firmware update process
    
    Workflow:
    1. Validate firmware file
    2. Prepare device for update
    3. Transfer firmware in chunks
    4. Verify transferred firmware
    5. Install firmware on device
    6. Verify installation and reboot
    """
    
    def __init__(self, server=None):
        self.server = server
        self.status = OTAStatus.IDLE
        self.progress = 0
        self.current_firmware = None
        self.target_devices = []
        self.update_thread = None
        self.cancel_flag = threading.Event()
        
        # Callbacks for GUI updates
        self.status_callback = None
        self.progress_callback = None
        self.log_callback = None
        
        # OTA configuration
        self.config = {
            "chunk_size": 1024,  # 1KB chunks
            "retry_attempts": 3,
            "timeout": 30,  # seconds
            "verify_checksum": True,
            "backup_current": True
        }
        
        logger.info("OTAHandler initialized")
    
    def set_callbacks(self, status_cb=None, progress_cb=None, log_cb=None):
        """Set callback functions for status updates"""
        self.status_callback = status_cb
        self.progress_callback = progress_cb
        self.log_callback = log_cb
        logger.debug("Callbacks set for OTA handler")
    
    def _update_status(self, status: OTAStatus, message: str = ""):
        """Update OTA status and notify callbacks"""
        self.status = status
        logger.info(f"OTA Status: {status.value} - {message}")
        
        if self.status_callback:
            self.status_callback(status, message)
        if self.log_callback:
            self.log_callback(f"[{status.value.upper()}] {message}")
    
    def _update_progress(self, progress: int):
        """Update progress and notify callbacks"""
        self.progress = progress
        if self.progress_callback:
            self.progress_callback(progress)
    
    def validate_firmware(self, firmware_path: str) -> Tuple[bool, Optional[FirmwareInfo]]:
        """
        Validate firmware file
        
        Returns:
            Tuple of (success, FirmwareInfo or None)
        """
        self._update_status(OTAStatus.VALIDATING, "Validating firmware file...")
        
        try:
            # Check if file exists
            if not os.path.exists(firmware_path):
                raise FileNotFoundError(f"Firmware file not found: {firmware_path}")
            
            # Get file info
            file_size = os.path.getsize(firmware_path)
            file_name = os.path.basename(firmware_path)
            
            # Calculate checksum
            checksum = self._calculate_checksum(firmware_path)
            
            # Extract version from filename or metadata
            version = self._extract_version(firmware_path)
            
            # Calculate number of chunks
            chunks = (file_size + self.config["chunk_size"] - 1) // self.config["chunk_size"]
            
            firmware_info = FirmwareInfo(
                file_path=firmware_path,
                file_name=file_name,
                file_size=file_size,
                checksum=checksum,
                version=version,
                chunks=chunks,
                chunk_size=self.config["chunk_size"]
            )
            
            self.current_firmware = firmware_info
            
            self._update_status(OTAStatus.IDLE, f"Firmware validated: {file_name} (v{version})")
            logger.info(f"Firmware validated: {firmware_info}")
            
            return True, firmware_info
            
        except Exception as e:
            error_msg = f"Firmware validation failed: {e}"
            self._update_status(OTAStatus.FAILED, error_msg)
            logger.error(error_msg)
            return False, None
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate MD5 checksum of file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _extract_version(self, file_path: str) -> str:
        """
        Extract version from firmware file
        Can be enhanced to read from file metadata or naming convention
        """
        # Simple extraction from filename
        # Expected format: firmware_v1.2.3.bin
        file_name = os.path.basename(file_path)
        if '_v' in file_name:
            version_part = file_name.split('_v')[1]
            version = version_part.replace('.bin', '').replace('.hex', '')
            return version
        
        # Check for version.txt in same directory
        version_file = Path(file_path).parent / "version.txt"
        if version_file.exists():
            with open(version_file, 'r') as f:
                return f.read().strip()
        
        # Default version
        return "1.0.0"
    
    def get_device_info(self, device_id: str = None) -> List[DeviceInfo]:
        """Get information about connected devices"""
        devices = []
        
        if self.server and hasattr(self.server, 'clients'):
            for client_id, client in self.server.clients.items():
                # Request device info through WebSocket
                device = DeviceInfo(
                    device_id=str(client_id),
                    current_version="Unknown",  # Should be requested from device
                    device_type="Generic",      # Should be requested from device
                    connection_status=True
                )
                devices.append(device)
        
        logger.debug(f"Found {len(devices)} connected devices")
        return devices
    
    def start_update(self, firmware_path: str, device_ids: List[str] = None) -> bool:
        """
        Start OTA update process
        
        Args:
            firmware_path: Path to firmware file
            device_ids: List of device IDs to update (None for all)
        
        Returns:
            Success status
        """
        if self.status != OTAStatus.IDLE:
            logger.warning("OTA update already in progress")
            return False
        
        # Validate firmware first
        success, firmware_info = self.validate_firmware(firmware_path)
        if not success:
            return False
        
        # Set target devices
        if device_ids:
            self.target_devices = device_ids
        else:
            # Update all connected devices
            self.target_devices = [d.device_id for d in self.get_device_info()]
        
        if not self.target_devices:
            self._update_status(OTAStatus.FAILED, "No devices available for update")
            return False
        
        # Start update in separate thread
        self.cancel_flag.clear()
        self.update_thread = threading.Thread(target=self._update_workflow)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        return True
    
    def _update_workflow(self):
        """Main OTA update workflow"""
        try:
            # 1. Prepare devices
            if not self._prepare_devices():
                return
            
            # 2. Transfer firmware
            if not self._transfer_firmware():
                return
            
            # 3. Verify firmware on device
            if not self._verify_firmware():
                return
            
            # 4. Install firmware
            if not self._install_firmware():
                return
            
            # 5. Complete and reboot
            self._complete_update()
            
        except Exception as e:
            error_msg = f"OTA update failed: {e}"
            self._update_status(OTAStatus.FAILED, error_msg)
            logger.exception("OTA update exception:")
    
    def _prepare_devices(self) -> bool:
        """Prepare devices for OTA update"""
        self._update_status(OTAStatus.PREPARING, "Preparing devices for update...")
        self._update_progress(5)
        
        for device_id in self.target_devices:
            if self.cancel_flag.is_set():
                self._update_status(OTAStatus.CANCELLED, "Update cancelled")
                return False
            
            # Send prepare command to device
            prepare_cmd = self._create_ota_command("PREPARE", {
                "firmware_size": self.current_firmware.file_size,
                "chunk_size": self.current_firmware.chunk_size,
                "chunks": self.current_firmware.chunks,
                "version": self.current_firmware.version
            })
            
            if self.server:
                self._send_to_device(device_id, prepare_cmd)
            
            time.sleep(0.5)  # Give device time to prepare
        
        self._update_progress(10)
        logger.info(f"Devices prepared for update: {self.target_devices}")
        return True
    
    def _transfer_firmware(self) -> bool:
        """Transfer firmware to devices in chunks"""
        self._update_status(OTAStatus.TRANSFERRING, "Transferring firmware...")
        
        if not self.current_firmware:
            return False
        
        try:
            with open(self.current_firmware.file_path, 'rb') as f:
                chunk_num = 0
                total_chunks = self.current_firmware.chunks
                
                while True:
                    if self.cancel_flag.is_set():
                        self._update_status(OTAStatus.CANCELLED, "Transfer cancelled")
                        return False
                    
                    # Read chunk
                    chunk_data = f.read(self.current_firmware.chunk_size)
                    if not chunk_data:
                        break
                    
                    # Send chunk to all target devices
                    for device_id in self.target_devices:
                        chunk_cmd = self._create_chunk_command(chunk_num, chunk_data)
                        if self.server:
                            self._send_to_device(device_id, chunk_cmd)
                    
                    chunk_num += 1
                    
                    # Update progress (10-80% for transfer)
                    progress = 10 + int((chunk_num / total_chunks) * 70)
                    self._update_progress(progress)
                    
                    # Small delay between chunks
                    time.sleep(0.01)
                
                logger.info(f"Firmware transfer complete: {chunk_num} chunks sent")
                return True
                
        except Exception as e:
            error_msg = f"Firmware transfer failed: {e}"
            self._update_status(OTAStatus.FAILED, error_msg)
            logger.error(error_msg)
            return False
    
    def _verify_firmware(self) -> bool:
        """Verify firmware on device"""
        self._update_status(OTAStatus.VERIFYING, "Verifying firmware on device...")
        self._update_progress(85)
        
        if not self.config["verify_checksum"]:
            logger.info("Checksum verification disabled")
            return True
        
        for device_id in self.target_devices:
            if self.cancel_flag.is_set():
                return False
            
            # Send verify command
            verify_cmd = self._create_ota_command("VERIFY", {
                "checksum": self.current_firmware.checksum
            })
            
            if self.server:
                self._send_to_device(device_id, verify_cmd)
            
            # Wait for verification response (simplified)
            time.sleep(1)
        
        self._update_progress(90)
        logger.info("Firmware verification complete")
        return True
    
    def _install_firmware(self) -> bool:
        """Install firmware on device"""
        self._update_status(OTAStatus.INSTALLING, "Installing firmware...")
        self._update_progress(95)
        
        for device_id in self.target_devices:
            if self.cancel_flag.is_set():
                return False
            
            # Send install command
            install_cmd = self._create_ota_command("INSTALL", {})
            
            if self.server:
                self._send_to_device(device_id, install_cmd)
            
            # Wait for installation
            time.sleep(2)
        
        logger.info("Firmware installation initiated")
        return True
    
    def _complete_update(self):
        """Complete update and reboot devices"""
        self._update_status(OTAStatus.COMPLETED, "Update completed successfully!")
        self._update_progress(100)
        
        # Send reboot command to devices
        for device_id in self.target_devices:
            reboot_cmd = self._create_ota_command("REBOOT", {})
            if self.server:
                self._send_to_device(device_id, reboot_cmd)
        
        logger.info("OTA update completed successfully")
    
    def cancel_update(self):
        """Cancel ongoing OTA update"""
        if self.status in [OTAStatus.TRANSFERRING, OTAStatus.PREPARING]:
            self.cancel_flag.set()
            logger.info("OTA update cancellation requested")
    
    def _create_ota_command(self, command: str, data: Dict) -> str:
        """Create OTA command JSON"""
        cmd = {
            "type": "ota_command",
            "command": command,
            "data": data,
            "timestamp": time.time()
        }
        return json.dumps(cmd)
    
    def _create_chunk_command(self, chunk_num: int, chunk_data: bytes) -> str:
        """Create firmware chunk command"""
        cmd = {
            "type": "ota_chunk",
            "chunk_num": chunk_num,
            "data": chunk_data.hex(),  # Convert bytes to hex string
            "size": len(chunk_data),
            "timestamp": time.time()
        }
        return json.dumps(cmd)
    
    def _send_to_device(self, device_id: str, command: str):
        """Send command to specific device"""
        if self.server and hasattr(self.server, 'send_to_client'):
            self.server.send_to_client(device_id, command)
        else:
            logger.warning(f"Cannot send to device {device_id}: Server not available")
    
    def get_status(self) -> Dict:
        """Get current OTA status information"""
        return {
            "status": self.status.value,
            "progress": self.progress,
            "firmware": self.current_firmware.__dict__ if self.current_firmware else None,
            "target_devices": self.target_devices
        }

class OTAManager:
    """
    Manager class for handling multiple OTA updates
    """
    
    def __init__(self, server=None):
        self.server = server
        self.handlers = {}  # Device-specific handlers
        self.default_handler = OTAHandler(server)
        
        logger.info("OTAManager initialized")
    
    def create_handler(self, handler_id: str) -> OTAHandler:
        """Create a new OTA handler"""
        handler = OTAHandler(self.server)
        self.handlers[handler_id] = handler
        return handler
    
    def get_handler(self, handler_id: str = None) -> OTAHandler:
        """Get OTA handler by ID or default"""
        if handler_id and handler_id in self.handlers:
            return self.handlers[handler_id]
        return self.default_handler
    
    def update_all_devices(self, firmware_path: str) -> bool:
        """Update all connected devices with same firmware"""
        return self.default_handler.start_update(firmware_path)
    
    def update_device(self, device_id: str, firmware_path: str) -> bool:
        """Update specific device"""
        return self.default_handler.start_update(firmware_path, [device_id])
    
    def get_all_status(self) -> Dict:
        """Get status of all OTA handlers"""
        status = {
            "default": self.default_handler.get_status()
        }
        for handler_id, handler in self.handlers.items():
            status[handler_id] = handler.get_status()
        return status