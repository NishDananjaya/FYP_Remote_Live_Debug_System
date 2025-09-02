# Embedded Vehicle Charger Live Debugging System  

A runtime debugging and monitoring framework for **vehicle chargers with distributed controllers**.  
This system allows engineers to remotely access microcontroller memory, monitor variables in real time, and perform efficient fault analysis.  

---

## 🚀 Features  
- **ELF File Parsing** – Extract variables, arrays, and structures with memory addresses.  
- **Remote Debugging Window** – IDE-like monitoring of live values without halting execution.  
- **Multi-Controller Support** – Works across charger subsystems: network, port, cabinet, and sensor controllers.  
- **WebSocket Communication** – Remote access to live runtime data.  
- **XCP Protocol Integration** – Network controller as XCP master; other controllers as XCP slaves over SPI/CAN.  
- **OTA Firmware Update (Planned)** – Future support for secure remote updates.  

---

## 📖 System Workflow  
1. Compile charger firmware → generates **ELF file**.  
2. User uploads ELF file to the **main module** (Raspberry Pi).  
3. ELF parser extracts variable addresses and types.  
4. Main device requests live values over **WebSocket**.  
5. **Charger network controller (XCP Master)** relays commands to subsystems over **SPI/CAN**.  
6. **XCP Slaves** return memory values.  
7. Data is displayed in a **real-time debugging window**.  

---


---

## ⚡ Advantages  
- Remote access – no physical connection required.  
- Non-intrusive runtime monitoring.  
- Easier fault analysis and faster troubleshooting.  
- Scalable for multiple chargers and cloud integration.  

---

## 🔮 Future Enhancements  
- Secure OTA update delivery.  
- Cloud dashboard for large-scale monitoring.  
- AI-based anomaly detection.  
- Fleet management integration.  

---

## 🛠️ Tech Stack  
- **Languages:** C / C++ (firmware), Python (tools), C++ (XCP stack)  
- **Protocols:** XCP, CAN, SPI, WebSocket  
- **Hardware:** Raspberry Pi, Vehicle Charger Controllers  

---

## 📌 Getting Started  
1. Clone the repository:  
   ```bash
   git clone https://github.com/your-org/charger-debugging-system.git

