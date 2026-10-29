"""Read-only asynchronous USB serial adapter; it never writes to a board."""

import queue
import threading
from typing import Callable, Optional

from devices.parser import UnitMessageParser, sanitize_diagnostic


def _open_pyserial(port: str, baudrate: int, timeout: float):
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("PySerial is not installed. Install dependencies with: python -m pip install -r requirements.txt") from exc
    return serial.Serial(port=port, baudrate=baudrate, timeout=timeout)


class SerialDeviceAdapter:
    def __init__(self, unit: str, port: str, parser: UnitMessageParser,
                 events: "queue.Queue[dict]", baudrate: int = 115200,
                 serial_factory: Optional[Callable] = None, timeout: float = 0.25) -> None:
        self.unit = unit
        self.port = port
        self.parser = parser
        self.events = events
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_factory = serial_factory or _open_pyserial
        self._stop = threading.Event()
        self._thread = None
        self._serial = None
        self._disconnect_requested = False

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def connect(self) -> None:
        if self.is_alive:
            raise RuntimeError(f"Unit {self.unit} serial worker is already running")
        self._stop.clear()
        self._disconnect_requested = False
        self._thread = threading.Thread(target=self._read_loop, name=f"serial-unit-{self.unit}", daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._disconnect_requested = True
        self._stop.set()

    def _emit(self, event_type: str, **data) -> None:
        self.events.put({"type": event_type, "unit": self.unit, **data})

    def _read_loop(self) -> None:
        serial_port = None
        try:
            serial_port = self.serial_factory(self.port, self.baudrate, self.timeout)
            self._serial = serial_port
            if self._stop.is_set():
                return
            self._emit("status", state="connected", port=self.port, baudrate=self.baudrate)
            while not self._stop.is_set():
                raw = serial_port.readline()
                if not raw:
                    # A read timeout is an idle poll, not a successful response.
                    continue
                if isinstance(raw, bytes) and not raw.endswith(b"\n"):
                    excerpt = sanitize_diagnostic(raw.decode("utf-8", errors="replace"))
                    self._emit("diagnostic", message=f"Incomplete serial line (no LF terminator): {excerpt}")
                    continue
                if isinstance(raw, str) and not raw.endswith("\n"):
                    self._emit("diagnostic", message=f"Incomplete serial line (no LF terminator): {sanitize_diagnostic(raw)}")
                    continue
                try:
                    line = raw.decode("utf-8").rstrip("\r\n") if isinstance(raw, bytes) else str(raw).rstrip("\r\n")
                except UnicodeDecodeError:
                    self._emit("diagnostic", message=f"Malformed serial line: invalid UTF-8 ({len(raw)} bytes)")
                    continue
                if not line:
                    continue
                parsed = self.parser.classify(line)
                self._emit("line", message=sanitize_diagnostic(line), classification=parsed.kind,
                           format_verified=parsed.format_verified)
        except Exception as exc:
            safe_error = sanitize_diagnostic(f"{type(exc).__name__}: {exc}")
            self._emit("error", message=safe_error)
        finally:
            self._serial = None
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception as exc:
                    self._emit("diagnostic", message=f"Error while closing serial port: {type(exc).__name__}")
            state = "operator-disconnect" if self._disconnect_requested else "disconnected"
            self._emit("status", state=state, port=self.port)


class UnitASerialAdapter(SerialDeviceAdapter):
    def __init__(self, port: str, events: "queue.Queue[dict]", **kwargs) -> None:
        from devices.parser import UnitAParser
        super().__init__("A", port, UnitAParser(), events, **kwargs)


class UnitBSerialAdapter(SerialDeviceAdapter):
    def __init__(self, port: str, events: "queue.Queue[dict]", **kwargs) -> None:
        from devices.parser import UnitBParser
        super().__init__("B", port, UnitBParser(), events, **kwargs)


class UnitCSerialAdapter(SerialDeviceAdapter):
    def __init__(self, port: str, events: "queue.Queue[dict]", **kwargs) -> None:
        from devices.parser import UnitCParser
        super().__init__("C", port, UnitCParser(), events, **kwargs)
