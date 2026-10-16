"""Cliente mínimo para adaptadores ELM327 (y clones/compatibles: Vgate, OBDLink…).

Transportes:
- TCP (adaptadores WiFi, normalmente 192.168.0.10:35000).
- Serie (USB, o Bluetooth clásico emparejado: /dev/rfcomm0 en Linux, /dev/tty.* en macOS).
  Requiere `pyserial`.
- BLE (los adaptadores pensados para iPhone). Requiere `bleak`.

Los parsers de respuesta son funciones puras para poder testearlos sin hardware.
"""
from __future__ import annotations

import asyncio
import re
import socket
import threading
import time
from typing import Optional, Sequence

from .dtc import decode_dtc_bytes
from .pids import decode_monitor_status, decode_pid

PROMPT = ">"

_NOISE = (
    "SEARCHING...", "BUS INIT", "STOPPED", "NO DATA", "UNABLE TO CONNECT",
    "CAN ERROR", "BUS ERROR", "DATA ERROR", "?", "OK", "ELM327",
)
_FRAME_PREFIX = re.compile(r"^([0-9A-F]):")


class ElmError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Parsers puros
# ---------------------------------------------------------------------------

def clean_lines(raw: str, echo: str = "") -> list[str]:
    """Respuesta cruda del ELM → líneas útiles (sin prompt, eco, espacios ni avisos)."""
    lines: list[str] = []
    for line in re.split(r"[\r\n]+", raw.replace(PROMPT, "")):
        line = line.strip().upper().replace(" ", "")
        if not line or (echo and line == echo.upper().replace(" ", "")):
            continue
        if any(line.startswith(n.replace(" ", "")) for n in _NOISE):
            continue
        lines.append(line)
    return lines


def hex_bytes(line: str) -> list[int]:
    line = _FRAME_PREFIX.sub("", line)
    if len(line) % 2 or not re.fullmatch(r"[0-9A-F]*", line):
        return []
    return [int(line[i : i + 2], 16) for i in range(0, len(line), 2)]


def _messages(lines: Sequence[str]) -> list[list[int]]:
    """Agrupa tramas ISO-TP ("0:", "1:"…) de CAN en un solo mensaje; el resto, una línea = un mensaje."""
    if any(_FRAME_PREFIX.match(l) for l in lines):
        joined: list[int] = []
        for line in lines:
            if _FRAME_PREFIX.match(line):
                joined.extend(hex_bytes(line))
        return [joined]
    return [b for b in (hex_bytes(l) for l in lines) if b]


def parse_mode01(lines: Sequence[str], pid: str) -> Optional[list[int]]:
    want = [0x41, int(pid, 16)]
    for msg in _messages(lines):
        if msg[:2] == want:
            return msg[2:]
    return None


def parse_supported(lines: Sequence[str], base: int) -> set[str]:
    data = parse_mode01(lines, f"{base:02X}")
    if not data or len(data) < 4:
        return set()
    bits = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
    return {f"{base + i + 1:02X}" for i in range(32) if bits & (1 << (31 - i))}


def parse_dtc_response(lines: Sequence[str], mode: str, is_can: bool) -> list[str]:
    """Modo 03/07/0A → códigos. En CAN el byte tras el de respuesta es el número de códigos."""
    response = int(mode, 16) + 0x40
    codes: list[str] = []
    for msg in _messages(lines):
        if not msg or msg[0] != response:
            continue
        data = msg[2:] if is_can else msg[1:]
        for code in decode_dtc_bytes(data):
            if code not in codes:
                codes.append(code)
    return codes


def parse_vin(lines: Sequence[str]) -> Optional[str]:
    raw: list[int] = []
    for msg in _messages(lines):
        # Cabecera 49 02 <nº de trama/ítems> en cada mensaje (CAN: uno solo; K-line: uno por línea).
        if msg[:2] == [0x49, 0x02]:
            raw.extend(msg[3:])
    text = "".join(chr(b) for b in raw if 48 <= b <= 57 or 65 <= b <= 90)
    return text[-17:] if len(text) >= 17 else None


def parse_voltage(lines: Sequence[str]) -> Optional[float]:
    for line in lines:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)V", line)
        if match:
            return float(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Transportes
# ---------------------------------------------------------------------------

class Transport:
    def write(self, data: bytes) -> None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def read_some(self, timeout: float) -> bytes:  # pragma: no cover - interfaz
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interfaz
        pass

    def read_until_prompt(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        buf = b""
        while PROMPT.encode() not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ElmError(f"Sin respuesta del adaptador en {timeout:.0f}s")
            buf += self.read_some(min(remaining, 0.5))
        return buf.decode("ascii", errors="ignore")


class TcpTransport(Transport):
    def __init__(self, host: str, port: int = 35000, connect_timeout: float = 5.0):
        self.sock = socket.create_connection((host, port), timeout=connect_timeout)

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def read_some(self, timeout: float) -> bytes:
        self.sock.settimeout(timeout)
        try:
            return self.sock.recv(1024)
        except socket.timeout:
            return b""

    def close(self) -> None:
        self.sock.close()


class SerialTransport(Transport):
    def __init__(self, port: str, baudrate: int = 38400):
        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise ElmError("Falta pyserial: pip install pyserial") from exc
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=0.5)

    def write(self, data: bytes) -> None:
        self.ser.write(data)

    def read_some(self, timeout: float) -> bytes:
        self.ser.timeout = timeout
        return self.ser.read(self.ser.in_waiting or 1)

    def close(self) -> None:
        self.ser.close()


class BleTransport(Transport):  # pragma: no cover - requiere hardware
    """GATT "serie" de los ELM327 BLE. Detecta solo la característica de escritura y la de
    notificación (FFE1 en Vgate/clones, FFF1/FFF2 en otros) si no se indican."""

    def __init__(self, address: Optional[str] = None, write_uuid: Optional[str] = None, notify_uuid: Optional[str] = None):
        try:
            from bleak import BleakClient, BleakScanner  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ElmError("Falta bleak: pip install bleak") from exc
        self._loop = asyncio.new_event_loop()
        # Proceso CLI normal (Raspberry/portátil), no el runtime embebido de iOS: un hilo
        # dedicado al event loop de bleak es lo más simple para exponer una API síncrona.
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._rx = bytearray()
        self._lock = threading.Lock()

        async def connect():
            target = address
            if not target:
                devices = await BleakScanner.discover(timeout=6.0)
                matches = [d for d in devices if d.name and re.search(r"OBD|ELM|VLINK|VGATE|IOS-VLINK|OBDLINK", d.name, re.I)]
                if not matches:
                    raise ElmError("No se encontró ningún adaptador OBD BLE (pasa --ble <dirección>)")
                target = matches[0].address
            client = BleakClient(target)
            await client.connect()
            w, n = write_uuid, notify_uuid
            for service in client.services:
                for char in service.characteristics:
                    if not n and "notify" in char.properties:
                        n = char.uuid
                    if not w and ("write" in char.properties or "write-without-response" in char.properties):
                        w = char.uuid
            if not (w and n):
                raise ElmError("El adaptador BLE no expone características de escritura/notificación")
            await client.start_notify(n, lambda _c, data: self._on_data(data))
            return client, w

        self._client, self._write_uuid = self._run(connect())

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=20)

    def _on_data(self, data: bytes) -> None:
        with self._lock:
            self._rx.extend(data)

    def write(self, data: bytes) -> None:
        self._run(self._client.write_gatt_char(self._write_uuid, data, response=False))

    def read_some(self, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._rx:
                    out = bytes(self._rx)
                    self._rx.clear()
                    return out
            time.sleep(0.02)
        return b""

    def close(self) -> None:
        try:
            self._run(self._client.disconnect())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------

class Elm327:
    def __init__(self, transport: Transport, timeout: float = 5.0):
        self.t = transport
        self.timeout = timeout
        self.is_can = True
        self.protocol = ""
        self.supported: set[str] = set()

    def command(self, cmd: str, timeout: Optional[float] = None) -> list[str]:
        self.t.write((cmd + "\r").encode("ascii"))
        return clean_lines(self.t.read_until_prompt(timeout or self.timeout), echo=cmd)

    def initialize(self) -> None:
        self.command("ATZ", timeout=8)
        for cmd in ("ATE0", "ATL0", "ATS0", "ATH0", "ATAT1", "ATSP0"):
            self.command(cmd)
        # La primera petición dispara la búsqueda automática de protocolo (puede tardar).
        self.supported = parse_supported(self.command("0100", timeout=20), 0x00)
        if not self.supported:
            raise ElmError("La ECU no responde: ¿contacto puesto y adaptador bien conectado?")
        dpn = self.command("ATDPN")
        self.protocol = dpn[0].lstrip("A") if dpn else ""
        self.is_can = self.protocol in {"6", "7", "8", "9"}
        base = 0x20
        while f"{base:02X}" in self.supported and base <= 0xC0:
            self.supported |= parse_supported(self.command(f"01{base:02X}"), base)
            base += 0x20

    def read_pid(self, key: str) -> Optional[float]:
        data = parse_mode01(self.command("01" + key), key)
        return decode_pid(key, data) if data is not None else None

    def read_monitor_status(self) -> Optional[dict]:
        data = parse_mode01(self.command("0101"), "01")
        return decode_monitor_status(data) if data and len(data) >= 4 else None

    def read_dtcs(self) -> dict[str, list[str]]:
        return {
            "stored": parse_dtc_response(self.command("03"), "03", self.is_can),
            "pending": parse_dtc_response(self.command("07"), "07", self.is_can),
            "permanent": parse_dtc_response(self.command("0A"), "0A", self.is_can),
        }

    def read_vin(self) -> Optional[str]:
        return parse_vin(self.command("0902", timeout=10))

    def battery_voltage(self) -> Optional[float]:
        return parse_voltage(self.command("ATRV"))

    def clear_dtcs(self) -> None:
        self.command("04", timeout=10)
