# Seguridad

Garaje es una app autoalojada de un solo propietario, **sin autenticación propia**: protégela
con un proxy con login (Authelia, Authentik, Cloudflare Access…) o accede por VPN (Tailscale,
WireGuard). `deploy/docker-compose.yml` publica el puerto **solo en 127.0.0.1** por defecto
(`GARAJE_BIND`).

Puntos específicos de este proyecto:

- **Cabeceras:** `nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` y, en las
  páginas, una CSP sin orígenes externos ni scripts en línea (`backend/app/security_headers.py`).
- **IA:** la clave del proveedor guardada desde *Ajustes* se cifra (Fernet, `GARAJE_SECRET_KEY` o
  una clave generada en el directorio de datos) y la API nunca la devuelve.
- **Ingesta OBD por token.** `/api/ingest/*` exige `Authorization: Bearer <token>` del
  vehículo. Solo se guarda el sha256 del token; regenerarlo invalida el anterior al
  instante. El token no da acceso al resto de la API.
- **Entradas acotadas.** CSV ≤ 20 MB y ≤ 200.000 lecturas por envío; claves de sensor
  con charset restringido; códigos DTC validados contra su formato; un CSV ya
  importado (mismo hash) se rechaza.
- **Escritura en la ECU** solo desde el agente y solo con `--clear-dtc` explícito
  (modo 04: borra códigos y apaga el MIL). La API nunca envía órdenes al coche.

Para reportar un problema de seguridad, usa el aviso privado de vulnerabilidades de GitHub
(*Security → Report a vulnerability* en el repositorio) en vez de abrir un issue público.
