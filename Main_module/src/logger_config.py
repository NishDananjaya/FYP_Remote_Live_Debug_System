"""
Logging configuration for the WebSocket Server Data Monitor application.
Provides structured logging for debugging and monitoring purposes.
"""
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

class CustomFormatter(logging.Formatter):
    """Custom log formatter with colors and detailed formatting"""
    
    # ANSI color codes
    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    
    # Format string with levelname, timestamp, filename, and message
    FORMATS = {
        logging.DEBUG: f"{GREY}%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s{RESET}",
        logging.INFO: f"{GREEN}%(asctime)s - %(name)s - %(levelname)s - %(message)s{RESET}",
        logging.WARNING: f"{YELLOW}%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s{RESET}",
        logging.ERROR: f"{RED}%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s{RESET}",
        logging.CRITICAL: f"{BOLD_RED}%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s{RESET}"
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def setup_logging(app_name="WebSocketServer", log_level=logging.INFO):
    """
    Set up comprehensive logging for the application.
    
    Args:
        app_name (str): Name of the application for log naming
        log_level: Logging level (default: INFO)
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create a timestamp for the log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{app_name}_{timestamp}.log"
    
    # Create logger
    logger = logging.getLogger(app_name)
    logger.setLevel(log_level)
    
    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger
    
    # Create console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(CustomFormatter())
    
    # Create file handler with detailed formatting
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)  # File gets all levels
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # Log startup information
    logger.info(f"Logging initialized. File: {log_file}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    return logger

# Create a default logger instance
logger = setup_logging()

# Function to get logger for specific modules
def get_module_logger(module_name):
    """
    Get a logger for a specific module with appropriate naming.
    
    Args:
        module_name (str): Name of the module
        
    Returns:
        logging.Logger: Configured logger for the module
    """
    return logging.getLogger(f"WebSocketServer.{module_name}")