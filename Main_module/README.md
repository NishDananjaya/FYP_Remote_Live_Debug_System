# WebSocket Server Data Monitor

A PyQt5-based graphical user interface for real-time data monitoring and device control through WebSocket communication.

## Overview

This application provides a comprehensive interface for:
- Real-time data monitoring and visualization
- Device parameter tuning
- Over-the-air (OTA) updates
- WebSocket-based communication with connected devices

## Features

- **Real-time Plotting**: Dynamic graphs showing parameter values over time
- **Multiple Parameter Monitoring**: Track voltage, current, and active ports simultaneously
- **Interactive Controls**: Start/stop monitoring and parameter selection
- **Data Logging**: Timestamped event log for all received data
- **Device Communication**: Send commands and write data to connected devices
- **Tabbed Interface**: Organized into Tuning, Monitoring, and OTA sections

## Project Structure

project/\
├── main.py # Main application entry point\
├── src/\
│ ├── server.py # WebSocket server implementation\
│ └── json_handler.py # JSON message processing utilities\
└── [README.md](https://readme.md/) # This file

text

## Installation

1. Ensure you have Python 3.7+ installed
2. Install required dependencies:
   ```bash
   pip install PyQt5 pyqtgraph websocket-server

Usage
-----

1.  Run the application:

    bash

    python main.py

2.  The WebSocket server will start on port 8000

3.  Connect your device to the WebSocket server

4.  Use the interface tabs:

    -   Tuning: Refresh parameters and write data to devices

    -   Monitoring: View real-time data plots and event logs

    -   OTA Updates: Placeholder for future firmware update functionality

Key Components
--------------

### Main Application (`main.py`)

The primary GUI application built with PyQt5 that includes:

-   Real-time plotting with `RealTimePlotWidget`

-   Tabbed interface for different functionalities

-   Status bar and logging system

-   Connection management to the WebSocket server

### WebSocket Server (`src/server.py`)

Handles client connections and message processing:

-   Manages multiple client connections

-   Processes incoming JSON messages

-   Implements monitoring loop for periodic data requests

-   Provides data writing functionality

### JSON Handler (`src/json_handler.py`)

Processes JSON messages with support for:

-   Response messages (command acknowledgments)

-   Data messages (parameter values)

-   Command creation (SET_MTA, UPLOAD, DOWNLOAD)

Communication Protocol
----------------------

The application uses a JSON-based protocol:

### Command Format

```json

{
  "type": "command",
  "command_id": "unique_id",
  "command": {
    "name": "COMMAND_NAME",
    "bytes": [byte1, byte2, ...]
  }
}
```
### Response Format

```json

{
  "type": "response",
  "command_id": "matching_id",
  "status": "success/error",
  "message": "description"
}
```
### Data Format

```json

{
  "type": "data",
  "parameter": "parameter_name",
  "value": 123.45,
  "timestamp": 1640995200.0
}
```
Supported Commands
------------------

1.  SET_MTA: Set memory transfer address

2.  UPLOAD: Request data from device (voltage, current, ports)

3.  DOWNLOAD: Write data to device

Customization
-------------

### Adding New Parameters

1.  Update `parameter_values` in the `DataMonitorGUI` class

2.  Add the parameter to the combo box in `setup_monitoring_tab()`

3.  Extend the monitoring loop in `server.py` to request the new parameter

### Modifying Plot Appearance

Adjust the `RealTimePlotWidget` class to:

-   Change colors and styles

-   Modify data retention (currently 1000 points)

-   Adjust grid and legend settings

Troubleshooting
---------------

1.  No data received: Check device connection to WebSocket server

2.  Plot not updating: Verify monitoring is started

3.  Write operations failing: Confirm device is properly connected and responsive

Future Enhancements
-------------------

-   OTA firmware update implementation

-   Additional parameter support

-   Export functionality for logged data

-   Customizable plot layouts

-   Authentication for WebSocket connectionss