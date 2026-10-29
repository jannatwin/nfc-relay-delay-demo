# Firmware integration mapping

This document records what the firmware source reviewed from the local
project copy does. The source sketches are intentionally excluded from this
public repository until embedded credentials are cleaned. This is a source
review only: no board was connected, no serial command was sent, and no
firmware was changed. The firmware files are the protocol authority; the JSON
examples in `SOFTWARE_DESIGN.md` are design proposals and are not emitted by
these sketches.

## Source files

| Unit | Role | Source reviewed |
|---|---|---|
| A | Verifier, local NFC reader, gate controller | `Unit_A_Verifier/Unit_A_Verifier.ino` (reviewed local source; not included here) |
| B | NFC reader and direct/relay route selector | `Unit_B_Reader/Unit_B_Reader.ino` (reviewed local source; not included here) |
| C | Transparent UDP relay | `Unit_C_Relay/Unit_C_Relay.ino` (reviewed local source; not included here) |

The design brief was reviewed in [`SOFTWARE_DESIGN.md`](../SOFTWARE_DESIGN.md).
No duplicate firmware copies were needed to resolve a source discrepancy.

## Serial framing and startup

All three sketches call `Serial.begin(115200)`. Unit A waits 800 ms after
initialization; B and C wait 500 ms. Unit A consumes commands into a 32-byte
line buffer, ignores `\r`, and dispatches on `\n` (at most 31 input characters
are retained). B and C consume one character at a time and do not require a
newline. B uppercases route characters; C accepts `+`, `-`, `p`, and `P` as
written. No sketch defines a formal serial protocol version or JSON format.

Output is human-readable text. `Serial.println` lines use the Arduino core's
line termination; `Serial.printf` format strings commonly include `\n`, and
some output is assembled from `Serial.print` fragments. Thus the source emits
newline-terminated messages but mixes output APIs; the exact byte-level line
ending should be confirmed against the actual board/core if a parser depends
on it. Startup text is not a structured handshake and Unit A's help banner
begins with a blank line.

| Unit | Initialization and source-backed startup/status text |
|---|---|
| A | `Unit A Wi-Fi AP: ...`, `Unit A IP: ...`, help banner, then either `Unit A PN532 ready.` or `Unit A PN532 not detected; remote Unit B can still report scans.`; OLED/status text includes `UNIT A READY`. The AP name is printed, but credentials are deliberately omitted here. See A lines 812–856. |
| B | `Unit B reader starting`; `Serial: D = direct to Unit A | R = route through Unit C relay`; then `PN532 ready. Tap a card/tag.` or `PN532 not found. Check SPI mode, wiring, and power.` Wi-Fi joining is printed during retries. See B lines 195–213 and 215–218. |
| C | `Unit C RELAY ATTACKER starting (not a card reader in this build)`; Wi-Fi join/status messages; `Relay listening on UDP ... , delay ... ms/hop.` and route help. See C lines 42–67 and 85–93. |

The firmware has no serial `connected` handshake. A USB serial port being open
means only that the host opened a port; readiness must be inferred cautiously
from the unit-specific text above. In particular, A can be operational as a
remote verifier when its local PN532 is absent.

## Commands accepted by each unit

### Unit A — newline-terminated command lines

`handleCommandLine` (A lines 520–570) trims leading spaces and dispatches on
the uppercased first character. Except for `T`, `U`, and `M`, trailing text is
not validated as a separate argument.

| Input syntax | Actual effect and validation |
|---|---|
| `N` | Enroll the next scanned tag as normal; maximum 6. A local scan enrolls locally; a remote B scan is enrolled only after valid proof. |
| `S` | Enroll the next scanned tag as simulated suspicious; maximum 2; same local/remote behavior as `N`. |
| `P` | Arm provisioning for the next local Unit A scan. Supported only for MIFARE Classic. A generates a secret if the card does not yield one, writes/reads it, and stores it in A's preferences; a card with an existing readable secret is stored. |
| `L` | Print enrollment lists and configuration, including UID and a provisioned/UID-only flag. |
| `X` | Erase enrolled-tag registry and cancel pending enrollment/provisioning. The source explicitly says secrets are kept. |
| `T<ms>` | Set persisted RTT threshold when parsed integer is 1–99,999 inclusive. Invalid values print `Usage: T<ms>, e.g. T60`. |
| `C` | Toggle calibration mode (not persisted). RTT bound is not enforced in calibration, but proof validation and role checks still apply. |
| `K` | Toggle and persist require-secret mode. |
| `G` | Start a gate test without a card. This actuates hardware and should not be exposed as a routine dashboard control without explicit operator intent. |
| `U`, `U+`, `U-`, `U<us>` | Adjust servo stop/neutral pulse by +5/-5 µs or set a value; clamp to 1000–2000 µs and persist. |
| `M<ms>` | Set and persist gate travel time for values 50–3000 ms. Invalid values leave current value and still print the current setting. |
| `H`, `?` | Print help. |

Unknown command initials are ignored. Exact handler and help text: A lines
352–365 and 520–581. Enrollment/provisioning implementation: A lines 765–809.

### Unit B — character commands

| Input | Actual effect |
|---|---|
| `D` or `d` | Route directly to Unit A; this is the default at boot. |
| `R` or `r` | Send to Unit C, which forwards to A. |

The handler is B lines 187–193; route defaults and target addresses are at B
lines 25–50. These change B's in-memory target and print either
`Target = Unit A DIRECT (legitimate path).` or
`Target = Unit C RELAY (attack path).` No newline is needed to enter the
character.

### Unit C — character commands

| Input | Actual effect |
|---|---|
| `+` | Add 10 ms per forwarded hop and print `Relay delay = <n> ms/hop`. |
| `-` | Subtract 10 ms, floored at 0, and print the delay. |
| `p` or `P` | Print the current delay. |

There is no exact numeric-set command. Delay starts at 40 ms/hop on every boot,
is not persisted, and has no upper bound in the handler (unsigned overflow is
possible after extreme repeated increments). See C lines 36–40 and 76–83. The
delay is applied before each forwarded UDP datagram (C lines 69–74).

## Messages and measurements

### Unit A decision, RTT, proof, and secret status

For a completed decision A emits a line in this format (A lines 447–452):

```text
Decision for B(net): uid=<UID> rtt=<N>ms proof=OK secret=yes
```

This is an illustrative template derived from the format string, not a literal
captured event. The source unit is `B(net)` or `A(local)`; proof is `OK`/`BAD`;
secret-used is `yes`/`no`. The line has no explicit decision field and no
threshold field. The following OLED `showScreen` output (also printed on
Serial) provides a human-readable result, for example:

```text
RELAY DETECTED | <UID> | RTT <N>ms > <threshold>ms
NORMAL: GATE OPEN | <UID> | RTT <N>ms - local OK
AUTH FAILED | <UID> | Bad credential proof
SIMULATED SUSPECT | <UID> | Gate remains closed
UNKNOWN TAG | <UID> | Not enrolled
```

The first two are representative display strings from A lines 457–489; the
display is emitted using `showScreen` at A lines 230–258. The “local OK” suffix
is also used for remote B decisions, so it must not be interpreted as the
source field. A decision is granted only after proof passes, the timing check
passes (unless calibration is on), and the UID is enrolled as normal. RTT
strictly greater than threshold is rejected; equality does not exceed the
bound. Suspicious and unknown UIDs are denied.

Unit A starts the `millis()` timer when it accepts a valid REQ and computes RTT
when a matching RESP arrives (A lines 655–665 and 683–687). This is the
authoritative **Wi-Fi challenge-response RTT**. Unit A's local-card path passes
`0` to the same decision function (A lines 797–809); that zero is a sentinel,
not a measured Wi-Fi RTT and must be shown as unavailable/local, not as a
0 ms network measurement.

When calibration is enabled A additionally prints:

```text
[CALIB] B(net) rtt=<N>ms proof=OK
```

This line reports RTT and proof but no access decision. It is emitted at A line
717. A threshold/configuration list uses:

```text
RTT threshold: <N> ms | require-secret: ON|off | calibrate: ON|off
```

The default threshold is 60 ms (A line 85); the active threshold is configured
and persisted by A, while RTT is measured by A. Calibration mode is volatile.
The human-readable decision line does not snapshot the threshold, so a parser
cannot reliably associate an arbitrary delayed threshold listing with a
particular decision without further protocol design.

Other A diagnostics include invalid/replayed REQ, invalid/missing/mismatched
RESP, and require-secret denial. These are not completed decision events in
all cases. An expired pending challenge is cleared silently; a later response
can produce `RESP: no matching challenge (expired or replayed).` Do not invent
a denied decision or RTT for missing/malformed replies. A's diagnostics are
documented by source at lines 647–665 and 681–717.

### Unit B serial output

B prints scan UID text (`Card UID: ...`), selected route, REQ send status,
challenge timeout/invalid challenge MAC, and response status. Representative
source-backed formats include:

```text
Sent REQ uid=<UID> via DIRECT
Sent REQ uid=<UID> via RELAY(Unit C)
No CHAL (timeout).
CHAL MAC invalid.
Sent RESP (secret=yes) local round-trip to send=<N>ms
```

See B lines 125–184 and 224–230. The “local round-trip to send” value is
measured by B around its own request/response activity and is **not** the
verifier RTT. B serial output includes the full card UID; a dashboard should
mask it in UI/diagnostic storage unless an explicit need and privacy policy
allow otherwise.

### Unit C status and forwarding output

C reports `Relay status: connected, IP = <ip>` or `Relay status: NOT connected
(will retry)`, and logs forwarded direction/byte count. It does not report A's
decision or RTT. It applies configured delay to each forwarded datagram. The
active delay is “configured”; the additional end-to-end RTT remains measured
only by A.

### UDP messages (not serial output)

The B↔A network protocol is comma-separated UDP text with truncated 32-hex
character MAC/proof fields in the packets. Source templates are:

```text
REQ,B,<reqid-hex>,<uid-hex>,<mac>
CHAL,<reqid-hex>,<nonce-hex>,<mac>
RESP,B,<reqid-hex>,<uid-hex>,<secret-flag>,<proof>,<mac>
```

These are templates derived from B lines 156–181 and A lines 636–680. They are
not dashboard serial messages. Unit C forwards packet bytes unchanged. No
secret, PSK, or HMAC literal/value is included in this document. The dashboard
should not parse or log network authentication fields.

## Value ownership

| Value | Authority / origin | Notes |
|---|---|---|
| Wi-Fi challenge-response RTT | Measured by Unit A | Only the `Decision for ... rtt=...` and `[CALIB] ... rtt=...` A output are verifier reports. Never substitute B's local elapsed time. |
| Access decision and proof validity | Decided by Unit A | Extract only from a complete recognized A result; source line does not encode the decision directly. |
| Threshold, require-secret, calibration | Configured/stateful on Unit A | Default threshold is 60 ms; `T` and `K` persist; `C` does not. A's decision line does not repeat active threshold. |
| Relay delay | Configured on Unit C | Default 40 ms per forwarded hop; `+`/`-` modify by 10 ms; volatile. |
| Direct/relay route | Configured on Unit B | Defaults to direct; `D`/`R` update the target. |
| Event receive time/session index | Generated by dashboard | Not emitted by firmware; must be labeled app-generated and must not enter RTT calculation. |
| Local Unit A card scan | A local path | A passes `0` into decision output; not a network RTT sample. |

## Integration cautions and unresolved items

1. The sketches use free-form text, not versioned structured messages. The A
   decision label appears in a separate display/status line; lines can be
   interleaved with startup, card, gate, and diagnostic output. Correlation and
   parser confidence need conservative handling.
2. `Decision for ...` prints an unmasked UID. B also prints a UID. Dashboard
   serial logging must redact it by default. Firmware does not print the card
   secret, PSK, or HMAC value, but such values exist in the UDP/authentication
   path; never capture packet payloads in the dashboard diagnostic log.
3. A's command protocol can trigger enrollment, provisioning, registry erase,
   and gate actuation. Do not send these automatically on connect; destructive
   and physical actions need explicit, well-confirmed UI workflows. `X` keeps
   stored secrets even though it erases enrollment.
4. Unit A's threshold is not included in each decision line. A reliable
   per-trial threshold snapshot cannot be guaranteed from arbitrary text logs
   if configuration changes or messages interleave.
5. A local scan's RTT `0` is ambiguous at the presentation boundary; the
   source comment explicitly says it represents local scanning. Treat it as
   missing/not applicable for network statistics.
6. Unit C's relay delay counter has no maximum and can wrap; `+`/`-` are the
   only controls, and the value resets on reboot.
7. Startup output and line endings depend partly on Arduino core implementation
   and serial monitor timing. Confirm captured output with the actual boards
   before enabling parsing. No hardware capture was made for this review.
8. Firmware contains hard-coded shared network/authentication credentials and
   a default MIFARE key. Their literal values are intentionally not reproduced
   here. This is a deployment security risk; rotate/rework them before using
   this setup beyond a controlled isolated demonstration.
9. Firmware help mentions direct/relay route on A's help output, but those
   commands are handled only by B. Send route selection only to Unit B.
10. Unit A's `NORMAL: GATE OPEN` text says `local OK` even for the network
    source. Use the explicit `source` field from `Decision for` instead.

Until a later integration milestone, these findings are a mapping only. They
do not authorize or implement serial commands from the dashboard.
