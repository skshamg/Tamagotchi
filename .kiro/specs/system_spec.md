# Specification: Neural Tamagotchi Desktop Harvester

## Core Functionality
- Transparent PyQt6 desktop daemon sitting above the Windows taskbar.
- Non-blocking telemetry thread polling RAM, CPU, and process memory via psutil.
- Safety whitelist: Explorer.exe, dwm.exe, winlogon.exe, and csrss.exe are protected.
- Finite State Machine with weighted animation transitions.