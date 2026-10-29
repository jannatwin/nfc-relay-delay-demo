# NFC Relay Delay Demo

Windows Tkinter dashboard with simulation mode and read-only USB serial
monitoring. Hardware mode opens separate serial connections to Units A, B, and
C at the documented 115200 baud. It does not send commands. Until the firmware
source and message contract are verified, serial lines are diagnostic text only
and cannot create a decision or RTT trial.

## Install and run

Install Python 3.10+ with Tcl/Tk, then from this directory run:

```powershell
python -m pip install -r requirements.txt
python main.py
```

The app starts in Simulation mode. Use **Settings → Hardware mode (read only)**
to enable port controls. Simulation and hardware modes are clearly labeled.

## Use the simulation

- On **Live Demo**, run a Direct Trial, Relay Trial, or the currently configured
  route. Example RTTs, proof/secret states, and outcomes are generated locally
  and are labeled simulated; they are never measurements from Unit A.
- Use the Calibration button to mark calibration demonstrations. In **Settings**,
  configure the simulated threshold, select the configured route, toggle the
  simulated require-secret scenario, and adjust simulated relay delay in
  10 ms-per-hop steps. These values affect simulation only.
- **Trials & Chart** shows in-memory simulated rows and separate direct/relay
  sample counts and RTT summaries. Small samples or overlapping ranges are
  inconclusive. Export CSV writes the current session; Clear Session asks for
  confirmation.
- **Cards** contains informational enrollment and provisioning guidance.
  Demo status buttons are local-only; no card secrets are accepted, displayed,
  or stored.

## Identify and connect the COM ports

1. Connect one ESP32 to the PC by USB.
2. Open Windows **Device Manager → Ports (COM & LPT)** and note the COM number
   that appears (for example, `COM5`). Disconnect and reconnect the board if
   needed to identify which entry belongs to it. The USB serial adapter name
   may also be shown there.
3. Repeat for Units A, B, and C, noting each port. Avoid assigning one COM port
   to more than one unit.
4. In the dashboard, select Hardware mode, choose each unit's COM port, leave
   baud at 115200, and click that unit's Connect button. Use Disconnect to
   close it. If a port is missing, install the board's USB serial driver and
   refresh the port list. Close Arduino Serial Monitor or other software that
   may already have the port open.

The worker reads LF-terminated lines and tolerates CRLF. The actual firmware
line endings are not available for verification. A partial line returned on a
read timeout is logged as incomplete and is not parsed.

## Verified and unresolved firmware interface

The project directory contains no ESP32 firmware source. The design brief
documents 115200 baud for all three units and mentions candidate text such as
`PN532 ready`, `Relay status: connected`, `Decision for ...`, and `[CALIB] ...
rtt=...`; it does not define exact line endings, full formats, startup order,
response timing, or command acknowledgements. The parsers mark these examples
as unverified candidates only. No command is sent on connect or by the UI, and
hardware serial text is never turned into a decision or RTT trial.
Hardware trial parsing, status interpretation, and route/calibration/threshold/
relay-delay commands remain disabled pending verified firmware source or
representative serial logs. Enrollment, erase, and provisioning commands are
also unsupported. The current hardware mode only opens and monitors USB serial
ports.

Diagnostics are kept in a bounded in-memory log and redact common secret, PSK,
HMAC, key, UID, and long-token patterns. No card secret is requested or stored.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests use mocked serial ports and do not require physical boards.
