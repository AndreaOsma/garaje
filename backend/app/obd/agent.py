"""Agente OBD: lee un ELM327 y sube lecturas, averías y monitores a Garaje.

Pensado para una Raspberry Pi en el coche (o un portátil): si el servidor no es
accesible (fuera de casa / sin tailnet), guarda cada lote en una cola local y la
vacía en cuanto vuelve a haber conexión.

    python -m app.obd.agent --server https://garaje.example.com \\
        --token <token del vehículo> --ble auto            # adaptador BLE (iPhone)
    python -m app.obd.agent ... --tcp 192.168.0.10:35000      # adaptador WiFi
    python -m app.obd.agent ... --serial /dev/rfcomm0         # USB / Bluetooth clásico

El token también puede ir en la variable GARAJE_TOKEN (preferible: no queda en el historial).
Solo usa la librería estándar (+ pyserial o bleak según el transporte).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .elm327 import BleTransport, Elm327, ElmError, SerialTransport, TcpTransport, Transport
from .pids import DEFAULT_POLL_PIDS

log = logging.getLogger("garaje.agent")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Uploader:
    def __init__(self, server: str, token: str, spool_dir: Path):
        # Solo http(s): urllib también abre file:// y similares.
        if urllib.parse.urlsplit(server).scheme not in ("http", "https"):
            raise ValueError("--server debe empezar por http:// o https://")
        self.url = server.rstrip("/") + "/api/ingest/snapshot"
        self.token = token
        self.spool = spool_dir
        self.spool.mkdir(parents=True, exist_ok=True)

    def _post(self, payload: dict) -> None:
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            method="POST",
        )
        # Esquema ya validado en __init__ (solo http/https).
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosemgrep: dynamic-urllib-use-detected
            if resp.status >= 300:
                raise urllib.error.HTTPError(self.url, resp.status, "error", resp.headers, None)

    def send(self, payload: dict) -> bool:
        """Envía (vaciando antes la cola pendiente). Si falla, encola y devuelve False."""
        try:
            self.flush()
            self._post(payload)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 422):
                # Token inválido o payload rechazado: reintentar no lo va a arreglar.
                log.error("El servidor rechazó el lote (%s); se descarta", exc.code)
                return False
            self._enqueue(payload)
        except (urllib.error.URLError, OSError) as exc:
            log.info("Servidor no accesible (%s); lote en cola", exc)
            self._enqueue(payload)
        return False

    def _enqueue(self, payload: dict) -> None:
        name = f"{time.time_ns()}.json"
        (self.spool / name).write_text(json.dumps(payload))

    def flush(self) -> None:
        for path in sorted(self.spool.glob("*.json")):
            self._post(json.loads(path.read_text()))
            path.unlink()
            log.info("Lote pendiente enviado: %s", path.name)


def _transport(args) -> Transport:
    if args.tcp:
        host, _, port = args.tcp.partition(":")
        return TcpTransport(host, int(port or 35000))
    if args.serial:
        return SerialTransport(args.serial, args.baud)
    return BleTransport(None if args.ble == "auto" else args.ble)


def run(args) -> int:
    token = args.token or os.getenv("GARAJE_TOKEN", "")
    if not token:
        log.error("Falta el token del vehículo (--token o GARAJE_TOKEN)")
        return 2
    uploader = Uploader(args.server, token, Path(args.spool).expanduser())
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]

    elm = Elm327(_transport(args))
    try:
        elm.initialize()
        poll = [p for p in DEFAULT_POLL_PIDS if p in elm.supported]
        log.info("Protocolo %s (CAN=%s); PIDs a leer: %s", elm.protocol, elm.is_can, ", ".join(poll))

        if args.clear_dtc:
            elm.clear_dtcs()
            log.warning("Códigos de avería borrados en la ECU (modo 04)")

        vin = elm.read_vin()
        samples: list[dict] = []
        started = time.monotonic()
        last_push = 0.0
        last_dtc = float("-inf")
        diag: dict = {}
        while True:
            ts = _now()
            for key in poll:
                value = elm.read_pid(key)
                if value is not None:
                    samples.append({"ts": ts, "key": key, "value": value})
            volts = elm.battery_voltage()
            if volts is not None:
                samples.append({"ts": ts, "key": "BATT", "value": volts})

            now = time.monotonic()
            if now - last_dtc >= args.dtc_every:
                diag = {"dtcs": elm.read_dtcs(), "monitor": elm.read_monitor_status()}
                last_dtc = now

            done = args.once or (args.duration and now - started >= args.duration)
            if done or now - last_push >= args.push_every:
                payload = {"session_id": session_id, "source": "agent", "samples": samples, "vin": vin, **diag}
                if uploader.send(payload):
                    log.info("Enviadas %d lecturas", len(samples))
                samples, diag, last_push = [], {}, now
            if done:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except ElmError as exc:
        log.error("%s", exc)
        return 1
    finally:
        elm.t.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.obd.agent", description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True, help="URL de tu Garaje (p.ej. https://garaje.example.com)")
    parser.add_argument("--token", help="token de ingesta del vehículo (o GARAJE_TOKEN)")
    link = parser.add_mutually_exclusive_group(required=True)
    link.add_argument("--tcp", help="adaptador WiFi host[:puerto] (por defecto puerto 35000)")
    link.add_argument("--serial", help="puerto serie (USB o Bluetooth clásico)")
    link.add_argument("--ble", help="dirección BLE del adaptador, o 'auto' para buscarlo")
    parser.add_argument("--baud", type=int, default=38400)
    parser.add_argument("--interval", type=float, default=2.0, help="segundos entre lecturas (2)")
    parser.add_argument("--push-every", type=float, default=60.0, help="segundos entre envíos (60)")
    parser.add_argument("--dtc-every", type=float, default=300.0, help="segundos entre lecturas de averías (300)")
    parser.add_argument("--duration", type=float, default=0, help="parar tras N segundos (0 = sin límite)")
    parser.add_argument("--once", action="store_true", help="una sola lectura completa y salir (útil en cron)")
    parser.add_argument("--clear-dtc", action="store_true", help="BORRA los códigos de avería y apaga el testigo MIL")
    parser.add_argument("--spool", default="~/.cache/garaje-agent", help="cola local de lotes sin enviar")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
