# NFC Relay Delay Demo — Software Design Brief

## 1. Purpose

Build a small operator dashboard for demonstrating and monitoring the existing
three-unit ESP32 project. The app should let a student connect to the boards,
run direct and relayed trials, view the verifier's decisions and RTT samples,
and prepare a clear demonstration for an instructor.

The dashboard is a **supervisory interface**. Unit A remains responsible for
the time-sensitive challenge-response measurement and the gate decision. The
app must not measure the RTT itself or make an access decision from desktop
timing.

## 2. Honest scope and terminology

The current firmware measures the **Wi-Fi challenge-response RTT between Unit
B and Unit A**. Unit C forwards those Wi-Fi messages and adds configurable
delay. The software should label this value **Wi-Fi challenge-response RTT**
or **measured verifier RTT**, not NFC radio RTT. The NFC card is read by Unit B
before the network exchange begins.

This is an educational relay-delay demonstration. A high RTT is an indication
that this exchange exceeded the selected timing threshold; it is not proof of
an NFC radio relay attack.

## 3. Intended users and main tasks

The primary user is a student presenting the prototype. They should be able to:

1. Confirm which ESP32 units are connected and ready.
2. Enroll and provision a demo card using Unit A.
3. Select a direct or relayed trial path.
4. Tap a card and see the verifier's result and RTT.
5. Repeat trials, compare direct and relayed measurements, and export results.
6. Adjust the threshold and relay delay for a controlled demonstration.

## 4. Recommended form

### First version: local desktop dashboard

Build a local desktop app on the laptop connected to the ESP32 boards by USB.
This is the simplest way to access the current Serial interfaces without
changing the Wi-Fi protocol. It can run without internet.

Suggested student-friendly stack:

- **Python** for the app and serial communication
- **PySerial** for USB serial ports
- **Tkinter** for a simple native interface, or **Flask** for a local browser UI
- **CSV** export for trial data

Choose Tkinter for the quickest working app. Choose Flask if the goal is a
browser-based presentation dashboard. Either option should keep serial access
in a backend service rather than in browser code.

### Later option: browser app over Wi-Fi

If the laptop should connect wirelessly, add a small authenticated control and
telemetry API to Unit A, or run a local bridge service connected to Unit A by
USB. Do not expose the existing unauthenticated serial commands directly to a
network. The current firmware has no dashboard API, so this option requires
firmware changes.

## 5. Layout and navigation

Use a clear, high-contrast layout that works on a classroom projector. Keep
navigation to these pages:

1. **Live Demo** — primary operator screen
2. **Trials & Chart** — measured results and comparisons
3. **Cards** — enrollment and secret-provisioning guidance
4. **Settings** — threshold, relay delay, serial ports, and demo mode

### Live Demo screen

This is the default screen. Organize it into three regions:

- **Device status row:** Unit A verifier, Unit B reader, Unit C relay; show
  connected/disconnected and last message time.
- **Trial controls:** `Direct trial`, `Relay trial`, `Calibration`, and `Stop`.
- **Latest decision card:** outcome, UID (optionally masked), source unit, RTT,
  configured threshold, proof status, secret status, and event time.

Use large status treatments:

- Green: `ACCESS GRANTED`
- Red: `ACCESS DENIED`
- Amber: `RELAY DELAY SUSPECTED`
- Gray: `WAITING FOR CARD` or `DEVICE DISCONNECTED`

Always include a short reason, such as `RTT 94 ms exceeded 60 ms` or
`Credential proof failed`. Do not use color alone to communicate a result.

### Trials & Chart screen

Show a table with columns:

| Column | Description |
|---|---|
| Time | Time the app received the event |
| Path | Direct or relayed |
| Reader | Unit B or local Unit A |
| RTT | Verifier-reported RTT in milliseconds |
| Threshold | Threshold active for that trial |
| Decision | Granted, denied, suspected delay, or error |
| Proof / secret | Validity and whether a card secret was used |

Include a simple dot plot or histogram comparing direct and relayed RTT
samples, plus sample count, minimum, median, maximum, and threshold. Explain
that overlap or a small sample size makes the result inconclusive. Provide
`Export CSV` and `Clear session` controls.

### Cards screen

Provide the steps and status for the existing Unit A enrollment workflow:

- Enroll as normal (`N`), then tap the card.
- Enroll as simulated suspicious (`S`), then tap the card.
- Provision a supported MIFARE Classic card secret (`P`) at Unit A's local
  reader.
- List enrollment (`L`) and display whether a secret is provisioned.

Show warnings before erase operations (`X`). Do not store card secrets in the
dashboard or include them in logs. Treat UIDs as demo identifiers and allow
masking them in the presentation view.

### Settings screen

Expose only settings supported by the connected firmware:

- Unit A serial port and baud rate (115200)
- Unit B serial port and baud rate (115200)
- Unit C serial port and baud rate (115200)
- RTT threshold in milliseconds (`T<ms>` on Unit A)
- Calibration mode (`C` on Unit A)
- Require-secret mode (`K` on Unit A)
- Relay delay in milliseconds per hop (`+` / `-` on Unit C)
- Direct/relay route (`D` / `R` on Unit B)

For the initial version, relay delay controls can use buttons that send the
existing `+` and `-` commands. Add a numeric delay field only after firmware
supports setting the exact value. Clearly show when a control is unavailable
because its unit is disconnected.

## 6. User flow for a classroom demonstration

1. Connect Units A, B, and C over USB and select their serial ports.
2. Wait until Unit A reports ready and Unit B and C are connected to Unit A's
   `NFC-DEMO` access point.
3. Enable calibration mode and perform several direct taps.
4. Review the direct RTT distribution and choose a threshold above the observed
   direct samples. Send the threshold to Unit A.
5. Run a direct trial and confirm the normal card is accepted.
6. Switch Unit B to relay mode and tap the same card.
7. Show Unit C's configured delay, the verifier-reported RTT, and the decision.
8. Export the trial table as CSV for the project report.

The app should identify which values are measured and which are configured:

- **Measured:** RTT reported by Unit A, decision, proof status, event source.
- **Configured:** threshold, relay delay, selected route, calibration mode.
- **App-generated:** event receive time and local session number.

## 7. Software architecture

```text
┌──────────────────────────────┐
│ UI: Live Demo / Trials /     │
│ Cards / Settings             │
└──────────────┬───────────────┘
               │ app events and commands
┌──────────────▼───────────────┐
│ Application controller       │
│ validates actions, updates   │
│ session and trial history    │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ Serial device adapters       │
│ Unit A / Unit B / Unit C     │
└───────┬──────────┬───────────┘
        │ USB      │
   ┌────▼───┐ ┌────▼───┐ ┌────▼───┐
   │Unit A  │ │Unit B  │ │Unit C  │
   │verify  │ │reader  │ │delay   │
   └────────┘ └────────┘ └────────┘
```

Keep serial reading asynchronous so the UI remains responsive. Give each board
its own adapter and parser. The application controller should translate
buttons into the current one-character/line commands, associate incoming logs
with a unit, and convert recognized messages into trial records.

## 8. Firmware integration

The current firmware prints human-readable serial text. A quick prototype can
parse known lines such as `Decision for ...`, `[CALIB] ... rtt=...`,
`PN532 ready`, and `Relay status: connected`, but parsing display text is
fragile. For a reliable app, add a structured event format to firmware while
preserving the existing hardware behavior.

Example newline-delimited JSON event from Unit A:

```json
{"type":"decision","source":"B(net)","uid":"E4D93F02","rtt_ms":94,"threshold_ms":60,"proof_valid":true,"secret_used":true,"decision":"relay_suspected"}
```

Example status event:

```json
{"type":"status","unit":"A","wifi_ap":true,"pn532_ready":true,"gate":"closed"}
```

Use a version field (for example, `"v":1`) in every structured message. Keep
each message on one line. Do not send the PSK, card secret, or full HMAC through
the dashboard event stream. The dashboard should not be placed in the
challenge-response path, so its processing cannot affect the verifier RTT.

## 9. Data model

Represent each completed attempt as:

```text
Trial {
  session_id
  received_at
  source_unit
  route                 // direct | relay | local
  uid_display           // optionally masked
  rtt_ms                // measured by Unit A; null for local scans
  threshold_ms
  proof_valid
  secret_used
  decision              // granted | denied | relay_suspected | error
  reason
}
```

Store the current session in memory and let the user export it to CSV. A local
database is unnecessary for the first version. If persistent storage is added,
make clearing it easy and avoid collecting names or other personal details.

## 10. Error and safety behavior

- If a board disconnects, show it clearly and disable commands for that board.
- If a serial message cannot be parsed, retain it in a diagnostic log; do not
  invent a decision or RTT.
- If a response times out, record `error` / `no response`, not a successful
  or confirmed relay decision.
- Confirm before clearing enrollment or session data.
- Keep the servo as a tabletop model-gate actuator. This software is not for a
  real access-control door.
- Never claim that millisecond Wi-Fi RTT is RF distance bounding or definitive
  proof of an NFC relay.

## 11. Suggested implementation milestones

1. **Serial monitor:** discover/select COM ports, connect, display raw output,
   send existing commands.
2. **Live demo:** parse known Unit A decisions and show the latest outcome.
3. **Three-unit controls:** route selection on B, delay adjustment on C, and
   Unit A threshold/calibration controls.
4. **Trials:** store structured session rows and export CSV.
5. **Firmware protocol cleanup:** emit versioned JSON-lines events and parse
   them instead of human-readable logs.
6. **Presentation polish:** add the comparison chart, connection indicators,
   masked UID mode, and a projector-friendly layout.

## 12. Acceptance criteria for the first useful version

- The app can connect to the three boards by their serial ports and show
  connection state.
- The operator can select direct/relay mode and see the active route.
- A completed attempt shows the decision and Unit A's reported RTT and
  threshold.
- A disconnected board or malformed message is shown as an error, not silently
  treated as an access decision.
- The app can export the current demonstration trials to CSV.
- The app clearly labels the measurement as Wi-Fi challenge-response RTT.

