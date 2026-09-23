# Todo
Add verbose output the spectrometer.
https://www.perplexity.ai/search/4e585054-2dfc-488f-b6fb-3926802c1b9f

background analysis. bei pressure gucken ob mbar or hpa. Die y achse ist oft auch nur ein wert. Entweder plots splitten oder mehrere achsen.
auch die telemtry_analysis.py umbennen oder ne ausgabe hinzufügen, dass man die selber nichta ausführen sollte.

Set a restart, if spectrometer gives an error.
set gyro frequeny higher.





# analysis
Add another plot analogus to the calibrated average hot and cold plot.The user selects a measurement folder for the tempertaure calibration. Afterwards he seelcts a folder of uncalibrated spectra. Then the calibration is applied to the uncalibrated spectra.Then the following formula is calculatd and plotted based on the calibratoin of the uncalibrated measurement. Tc is the median cold load temperature from bin 614 to 1843. Th-Tc is computed using compute_median_hot_cold_distanceTc+(Th-Tc)*(Pc-Ph_shifted)/(Ph-Ph_shifted)



# Project structure improvements

## Goals
- Make the Python code importable and testable as a package (no `sys.path.append(...)` hacks).
- Keep systemd as the runtime orchestration layer, but make it easy to run locally/dev and to validate service health.
- Consolidate UDP protocol/client logic so the main control script and servers share consistent behavior.
- Centralize configuration (ports/hosts/paths) so systemd units and Python stay in sync.

==================================================
Fehler RaspberryPi
==================================================

Script muss mit sudo rechten ausgeführt werden. 
Also entweder in bash mit cd in den Ordner. Dann my sudo python3 ausführen und
direkt in python öffnen exec(open('pmc_backend3_Martin.py').read()).
Oder z.B. thonny mit sudo öffnen.


Zuerst pmc_backend ausführen damit die Befehle funktionieren.
pmc_udpserver ausführen im Labview zu benutzen.



Fehler:
Man kann connecten, aber sobald man das Spektrometer initialisiert kommt der Fehler
"""
pmc.setupPMCC(load('allregs.bin'), bandwidth='2GHz',int_time_ms=500) 
b"This handle hasn't been activated yet"
Traceback (most recent call last):
  File "<pyshell>", line 1, in <module>
  File "/home/pi/Documents/PythonProjects/Pacific_MicroChip_EVAL2_PCB/python/pmc_backend_v4_Lukas.py", line 273, in setupPMCC
    if self.readReg(0)!=6: raise Exception('setupPMCC: connection error')
  File "/home/pi/Documents/PythonProjects/Pacific_MicroChip_EVAL2_PCB/python/pmc_backend_v4_Lukas.py", line 183, in readReg
    buf=self._readReg(reg,1)
  File "/home/pi/Documents/PythonProjects/Pacific_MicroChip_EVAL2_PCB/python/pmc_backend_v4_Lukas.py", line 177, in _readReg
    buf=sendread_packet(self.pd,seq)
  File "/home/pi/Documents/PythonProjects/Pacific_MicroChip_EVAL2_PCB/python/pmc_backend_v4_Lukas.py", line 61, in sendread_packet
    buf=read_next(pd)
  File "/home/pi/Documents/PythonProjects/Pacific_MicroChip_EVAL2_PCB/python/pmc_backend_v4_Lukas.py", line 43, in read_next
    if perr!=b'': print(perr); raise Exception('read next: perr')
Exception: read next: perr
"""

Lösung:
Connect Befehl war nicht erfolgreich, was man an 
"setnonblock: -3" sieht. -1 is a general failure code for libpcap, but -3 usually means invalid handle or unactivated handle.

In "def connect" muss erst "pcap.activate(self.pd)" und dann "pcap.setnonblock(self.pd,1, self.ebuf)" gesetzt werden. Das war einfach die Reihenfolge falsch.






==================================================
Fehler allgemein
==================================================
Wenn <-: b'INIT 2GHz 500'
cannot execute command: sendread_packet: timeout, Data:False
Spektrometer neustarten

val=pmc.readReg(336)&0b110
list(BANDWIDTH.keys())[list(BANDWIDTH.values()).index(pmc.readReg(336)&0b11)]

==================================================
Noch in Arbeit
==================================================
with open('your_file.txt', 'w') as f:
    for line in adc:
        f.write(f"{line}\n")




for i in range(1):
	d,t=pmc.measSpectra(1)
	y=dt(t)
	for x in range(len(y)):
    		print("%.2f" % y[x])
==================================================
Als CSV speichern:
np.savetxt('data.csv', (col1_array, col2_array, col3_array), delimiter=',')
        np.savetxt('E:\Messungen\2024_05_03_Compact_Spectrometer\test.csv', (1233, 123,123), delimiter=',')




ADC auslesen
a=pmc.readADC()
hist,_=np.histogram(adcm,bins=32,range=(0,63)) #_ ist einfach ne Variable, die nie verwendet wird. Daher wird der zweite returnvalue irgnoriert.
20

Bem.:
a=pmc.readADC()
len(a)=20
len(a[0])=1024
adcm=sum(a,[]) #also 1 1D arrays, wobei jedes Element ein 2D Array ist.
len(adcm) = 20480


fn="ADC_ E:\\Messungen\\2024_05_03_Compact_Spectrometer\\20240617_Testing_python_Interface".split(' ')
datetime=time.strftime("%Y%m%d%H%M%S", time.localtime(time.time()))
fn=params[1]+ "\\" +  f'{datetime}' + 'ADC.csv'
pmc.saveADC(fn)









1GHz: 0b101010001000&110
2GHz. 0b101010001010&
4GHz: 0b101010001100&
8GHz: 0b101010001110&



---

## 1) Repo layout (filesystem)
- [ ] Create standard top-level folders:
  - [ ] `src/balloon_mission/` for Python package code
  - [ ] `scripts/` for developer/operator helper scripts (shell)
  - [ ] `systemd/` for `.service` / `.timer` / unit templates and install notes
  - [ ] `config/` for runtime config templates (e.g., TOML/YAML/JSON)
  - [ ] `tests/` for unit/integration tests
  - [ ] `docs/` for operator docs (optional but recommended)

- [ ] Move current helper scripts into `scripts/`
  - [ ] `run_services.sh` -> `scripts/run_services.sh`
  - [ ] `check_services.sh` -> `scripts/check_services.sh`
  - [ ] `run_python_measurement.sh` -> `scripts/run_python_measurement.sh` (if present)

- [ ] Put systemd unit files (or templates) under `systemd/`
  - [ ] `balloon-main.service`
  - [ ] `balloon-udp@.service`
  - [ ] `balloon-udp-spectrometer.service`
  - [ ] Add `systemd/README.md` with install instructions and paths.

---

## 2) Package-ify Python (remove `sys.path.append`)
- [ ] Add `pyproject.toml` (setuptools or hatch/poetry) using a `src/` layout.
- [ ] Create package skeleton:
  - [ ] `src/balloon_mission/__init__.py`
  - [ ] `src/balloon_mission/main_control.py` (logic currently in `run_measurement.py`)
  - [ ] `src/balloon_mission/udp/` (shared UDP client + protocol)
  - [ ] `src/balloon_mission/devices/` (device-level wrappers)

- [ ] Convert `run_measurement.py` into a thin entry script:
  - [ ] Keep CLI parsing there (or move into package as `balloon_mission.cli`)
  - [ ] Import `balloon_mission.main_control:main`
  - [ ] Remove `sys.path.append(os.path.join(..., 'src'))`

---

## 3) Unify UDP client + protocol
- [ ] Create a shared UDP client module (used by main control and tests)
  - [ ] Standard timeout/retry strategy
  - [ ] Consistent receive framing (newline-terminated vs fixed-length)
  - [ ] Consistent error handling (timeouts, partial reads)

- [ ] Define protocol helpers/types (even if “simple strings + JSON”)
  - [ ] Normalize response format for all servers: `{status: ok|err, ...}`
  - [ ] Add strict JSON decode + clear error messages
  - [ ] Decide whether commands are newline-terminated everywhere

- [ ] Replace `cmd()` in `run_measurement.py` with the shared client

---

## 4) Central configuration (ports/host/paths)
- [ ] Create a single configuration source:
  - [ ] `config/default.toml` (or `yaml/json`)
  - [ ] Include: host, ports per service, output roots, default timeouts

- [ ] Make main control read config (CLI flags override config)
- [ ] Make systemd units read the same values (via EnvironmentFile or templating)
  - [ ] Add `config/balloon.env.example` for systemd `EnvironmentFile=...`

---

## 5) Entry points and operator UX
- [ ] Provide a single “operator” entrypoint:
  - [ ] `scripts/run_services.sh` (enable/start/disable)
  - [ ] Optional: `scripts/health_check.sh` or a Python `balloon-health` command

- [ ] Add `README.md` sections:
  - [ ] Quick start (systemd install + starting services)
  - [ ] Running a measurement
  - [ ] Viewing logs (`journalctl -fu ...`)
  - [ ] Where data is written and how it is named

---

## 6) Logging + observability
- [ ] Standardize logging across:
  - [ ] UDP servers
  - [ ] main control
  - [ ] analysis scripts (optional)

- [ ] Ensure logs go to stdout/stderr (journald-friendly)
- [ ] Add a simple “device server health” command:
  - [ ] Each server implements `PING` / `STATUS` returning JSON
  - [ ] Main control can assert everything is up before starting

---

## 7) Testing strategy
- [ ] Unit tests:
  - [ ] Protocol parsing (JSON decode, framing)
  - [ ] UDP client behavior (mock sockets)
  - [ ] Main control sequencing logic (mock client)

- [ ] Integration tests (optional):
  - [ ] Spawn a dummy UDP server in tests and verify end-to-end send/recv
  - [ ] Smoke test: service ports reachable on localhost

---

## 8) Gradual migration plan (minimize downtime)
- [ ] Step 1: introduce package + shared UDP client while keeping current scripts working
- [ ] Step 2: move scripts to `scripts/`, keep root-level stubs that forward (optional)
- [ ] Step 3: migrate systemd units into `systemd/` + document install
- [ ] Step 4: enforce config centralization and remove duplicate port constants
- [ ] Step 5: add tests + CI (optional)

---

## Notes / current hotspots
- `run_measurement.py` currently:
  - embeds ports/constants
  - implements `cmd()` socket logic inline
  - modifies `sys.path` to import from `src/`
- `run_services.sh`:
  - works well as an operator helper, but belongs under `scripts/`
  - should be documented alongside systemd unit files
