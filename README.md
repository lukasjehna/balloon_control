# Overview

# Structure
- `src/l` python source code
- `config/` mission settings
- `data/` telemetry and data saved during the mission
- `logs/` Event and debug logs

# Installation
## libpcap
grant the CAP_NET_RAW capabilities so libpcap can access raw data stream, so you don't need sudo python3.
sudo setcap cap_net_raw+ep $(readlink -f $(uv python find))

# Quick start
## start a full measurement
./script/run_service 
## device scripts
try uv run script.py
sometimes python3 script.py might be needed.


# Documentation
- systemd and service managment -> docs/systemd.md
- Data analyis -> docs/analysis.md
- Hardware -> docs/hardware.md
- Development -> docs/development.md

# Development
