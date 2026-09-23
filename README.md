# Overview

# Structure
- `src/l` python source code
- `config/` mission settings
- `data/` telemetry and data saved during the mission
- `logs/` Event and debug logs

# Installation

# Quick start
## start a full measurement
./script/run_service 
## analysis
uv run python -m src.balloon.analysis.noise_temperature_folder_viewer --thot 300 --tcold 5 --pairs-per-average 30 --spectral-bin-size 3

# Documentation
- systemd and service managment -> docs/systemd.md
- Data analyis -> docs/analysis.md
- Hardware -> docs/hardware.md
- Development -> docs/development.md

# Development
