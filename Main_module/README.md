# WebSocket Device Monitor & OTA Manager  
### *Real-Time Memory Inspection, Dynamic Tuning & Secure Firmware Updates*

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/downloads/) [![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green)](https://www.riverbankcomputing.com/software/pyqt/) [![WebSocket](https://img.shields.io/badge/Protocol-WebSocket-orange)](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API) [![OTA Ready](https://img.shields.io/badge/OTA-Ready-brightgreen)](#) [![ELF Parser](https://img.shields.io/badge/ELF-pyelftools-purple)](#)

---

**A full-stack embedded debugging and deployment suite** — monitor live variables, write to memory on-the-fly, and push firmware updates over WebSocket. Built for developers working with STM32, ESP32, or any MCU with WebSocket/XCP-like capabilities.

---

## Core Capabilities

- **Live Memory Monitoring** – Poll scalar/array variables at 100+ Hz  
- **Instant Write Access** – Modify RAM values directly from GUI  
- **OTA Firmware Flashing** – Chunked, verified, resumable updates  
- **ELF to CSV Auto-Mapping** – Extract symbols & generate memory maps  
- **Multi-Client WebSocket Server** – Thread-safe, JSON-based protocol  
- **Interactive PyQt5 Dashboard** – Plots, tables, logs, and export tools  

---

## Technologies

| Layer               | Technology                                  |
|---------------------|---------------------------------------------|
| **Language**        | Python 3.8+                                 |
| **GUI**             | PyQt5 + pyqtgraph (live plotting)           |
| **Networking**      | `websocket-server` (async-ready)            |
| **ELF Parsing**     | `pyelftools` (DWARF introspection)          |
| **Data Handling**   | `pandas`, `numpy`, `csv`                    |
| **Logging**         | Custom colored + rotating file logger       |
| **Threading**       | `threading`, `concurrent.futures`, `queue`  |
| **File System**     | `pathlib` (modern path handling)            |

---

## Project Structure

```
.
├── main.py                  # Launch GUI
├── src/
│   ├── server.py            # WebSocket server + protocol engine
│   ├── gui.py               # Full PyQt5 interface (tabs, graphs, OTA)
│   ├── json_handler.py      # JSON command/response parser
│   ├── ota_handler.py       # Firmware transfer & verification logic
│   ├── mem_map_byelf.py     # .elf → .csv variable extractor
│   ├── logger_config.py     # Colorful + rotating logs
│   └── testpath.py          # Path verification tool
├── data/elf/                # Input firmware binaries
├── data/csv/                # Generated memory maps
├── logs/                    # Auto-rotating log files
```

---

## Quick Start

```bash
git clone https://github.com/yourusername/websocket-device-monitor.git
cd websocket-device-monitor
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 1. Generate Memory Map
```bash
python src/mem_map_byelf.py
# → data/csv/XCP_slave_disco_*.csv
```

### 2. Launch Application
```bash
python main.py
```

---

## JSON Protocol (Device ↔ Server)

```json
// Initialize debug session
{"cmd": "init", "con_id": "01"}

// Read 32-bit value
{"cmd": "mem_read", "add": "0x20000100", "size": "32"}

// Write value (auto-converted to binary)
{"cmd": "mem_write", "add": "0x20000100", "size": "32", "data": "0b00000000000000000000000000001010"}

// Terminate session
{"cmd": "end", "con_id": "01"}
```

**Responses**:
```json
{"res": "mem_read", "add": "0x20000100", "value": "42"}
{"res": "mem_write", "state": "success"}
```

---

## GUI Highlights

- **Monitoring Tab** – Live plots + editable table  
- **OTA Tab** – Select `.bin`, view progress, cancel anytime  
- **Log Console** – Real-time, filterable, color-coded  
- **Export** – CSV or Excel with timestamps  

---

## Development & Contribution

```bash
# Run tests
python -m unittest discover

# Add feature → test → PR
```

We welcome:
- New data type support (`float`, `double`, structs)
- Protocol extensions (streaming, events)
- GUI themes & accessibility
- Dockerization

---

## Debugging

- Logs: `logs/WebSocketServer_*.log`
- Enable debug: Edit `logger_config.py` → `log_level=logging.DEBUG`
- Path issues? Run `python src/testpath.py`

---

**Precision control for embedded systems — monitor, tune, update, repeat.**  
*No JTAG. No serial. Just WebSocket magic.*
