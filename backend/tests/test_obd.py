"""Decodificación OBD sin hardware: PIDs, DTC, monitores, ELM327 (transporte simulado) y CSV."""
from datetime import date, timezone
from zoneinfo import ZoneInfo

from app.obd.carscanner import parse_csv
from app.obd.dtc import decode_dtc_pair, describe_dtc
from app.obd.elm327 import (
    Elm327,
    Transport,
    clean_lines,
    parse_dtc_response,
    parse_mode01,
    parse_supported,
    parse_vin,
)
from app.obd.pids import decode_monitor_status, decode_pid, key_for_label


def test_decode_pids():
    assert decode_pid("0C", [0x1A, 0xF8]) == 1726.0
    assert decode_pid("05", [0x7B]) == 83.0
    assert decode_pid("06", [0x80]) == 0.0
    assert decode_pid("A6", [0x00, 0x0F, 0x42, 0x40]) == 100000.0
    assert decode_pid("0C", [0x1A]) is None


def test_decode_dtc():
    assert decode_dtc_pair(0x01, 0x33) == "P0133"
    assert decode_dtc_pair(0x44, 0x35) == "C0435"
    assert decode_dtc_pair(0xC1, 0x00) == "U0100"
    assert decode_dtc_pair(0x00, 0x00) is None
    assert describe_dtc("P0420")["severity"] == "media"
    assert "fabricante" in describe_dtc("P1234")["description"]
    assert describe_dtc("P0999")["generic"] is True


def test_monitor_status_diesel_not_ready():
    # MIL encendido + 2 códigos; diésel (bit 3 de B); DPF disponible e incompleto.
    status = decode_monitor_status([0x82, 0x0F, 0x40, 0x40])
    assert status["mil_on"] is True and status["dtc_count"] == 2
    assert status["ignition"] == "compresión"
    dpf = next(m for m in status["monitors"] if m["name"] == "Filtro de partículas")
    assert dpf["complete"] is False
    assert status["ready"] is False


def test_elm_parsers_can_and_kline():
    lines = clean_lines("010C\r410C1AF8\r\r>", echo="010C")
    assert parse_mode01(lines, "0C") == [0x1A, 0xF8]
    assert parse_supported(["4100BE1FA813"], 0) >= {"01", "03", "04", "05", "0C", "0D", "20"}
    # CAN multitrama: 4 códigos.
    can = ["00A", "0:430401330300", "1:C1000420000000"]
    assert parse_dtc_response(can, "03", is_can=True) == ["P0133", "P0300", "U0100", "P0420"]
    # K-line: una línea por mensaje, sin byte de recuento.
    assert parse_dtc_response(["43013303000000"], "03", is_can=False) == ["P0133", "P0300"]
    assert parse_dtc_response(["4300"], "03", is_can=True) == []


def test_parse_vin_can():
    vin = "WVWZZZ1KZAW000001"
    payload = [0x49, 0x02, 0x01] + [ord(c) for c in vin]
    hexes = "".join(f"{b:02X}" for b in payload)
    frames = ["014", f"0:{hexes[:12]}", f"1:{hexes[12:26]}", f"2:{hexes[26:]}"]
    assert parse_vin(frames) == vin


class FakeTransport(Transport):
    def __init__(self, replies: dict[str, str]):
        self.replies = replies
        self.pending = b""
        self.sent: list[str] = []

    def write(self, data: bytes) -> None:
        cmd = data.decode().strip()
        self.sent.append(cmd)
        self.pending = (self.replies.get(cmd, "NO DATA") + "\r\r>").encode()

    def read_some(self, timeout: float) -> bytes:
        out, self.pending = self.pending, b""
        return out


def test_elm327_session_with_fake_adapter():
    fake = FakeTransport({
        "ATZ": "ELM327 v1.5", "ATE0": "OK", "ATL0": "OK", "ATS0": "OK", "ATH0": "OK", "ATAT1": "OK", "ATSP0": "OK",
        "0100": "SEARCHING...\r4100BE1FA813", "0120": "41208005B015", "ATDPN": "A6",
        "010C": "410C0FA0", "0101": "41018307E500", "03": "4302010301700000",
        "07": "4300", "0A": "4A00", "ATRV": "12.4V",
    })
    elm = Elm327(fake)
    elm.initialize()
    assert elm.is_can and "0C" in elm.supported
    assert elm.read_pid("0C") == 1000.0
    assert elm.battery_voltage() == 12.4
    assert elm.read_dtcs() == {"stored": ["P0103", "P0170"], "pending": [], "permanent": []}
    assert elm.read_monitor_status()["mil_on"] is True


def test_key_for_label_aliases():
    assert key_for_label("Engine RPM") == ("0C", True)
    assert key_for_label("Revoluciones del motor") == ("0C", True)
    assert key_for_label("Velocidad del vehículo") == ("0D", True)
    key, standard = key_for_label("Boost pressure (turbo)")
    assert not standard and key.startswith("cs:")


def test_parse_carscanner_long_format():
    csv = (
        '"SECONDS";"PID";"VALUE";"UNITS"\n'
        '"49700.5";"Engine RPM";"850";"rpm"\n'
        '"49700.5";"Engine coolant temperature";"88";"°C"\n'
        '"49701.5";"Boost pressure";"1,2";"bar"\n'
        '"86399.0";"Engine RPM";"900";"rpm"\n'
        '"2.0";"Engine RPM";"910";"rpm"\n'
    ).encode()
    log = parse_csv(csv, date(2026, 7, 1), ZoneInfo("Europe/Madrid"))
    assert len(log.samples) == 5
    first = log.samples[0]
    # 13:48:20.5 hora de Madrid (UTC+2 en verano) = 11:48:20.5 UTC
    assert first[0].astimezone(timezone.utc).hour == 11 and first[1] == "0C"
    assert log.samples[2][2] == 1.2
    assert "cs:boost-pressure" in log.sensors
    # Paso por medianoche → día siguiente.
    assert log.samples[-1][0].date() == date(2026, 7, 1) and log.samples[-1][0] > log.samples[-2][0]


def test_parse_wide_format():
    csv = b"Time,Engine RPM (rpm),Vehicle speed (km/h)\n0,800,0\n1,1500,12\n"
    log = parse_csv(csv, date(2026, 1, 1))
    assert {k for _, k, _ in log.samples} == {"0C", "0D"}


def test_agent_rejects_non_http_server(tmp_path):
    import pytest
    from app.obd.agent import Uploader

    with pytest.raises(ValueError):
        Uploader("file:///etc/passwd", "t", tmp_path)
    assert Uploader("https://garaje.example", "t", tmp_path).url.endswith("/api/ingest/snapshot")
