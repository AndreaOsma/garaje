# Garaje

Gestión de tus vehículos, autoalojada: mantenimiento (plan por km/meses e historial de taller),
repostajes con consumo real, gastos y coste por km, vencimientos (ITV, seguro, impuesto…) y
**diagnóstico OBD-II automatizable**: averías explicadas en español, testigo MIL, monitores de
emisiones para la ITV, tensión de batería y alternador y sesiones de conducción con gráficas.

- **Backend:** FastAPI (Python 3.12) + SQLAlchemy + Alembic + SQLite
- **Frontend:** Vite + React + TypeScript, con visor 3D (three.js) del coche y del motor por dentro
- **Sin login en la app:** ponla detrás de tu proxy con login o de una VPN ([más abajo](#seguridad)).
- **IA a tu elección (opcional):** Claude, Gemini, OpenRouter u Ollama para investigar los códigos de avería de tu marca.
- **Código:** [github.com/AndreaOsma/garaje](https://github.com/AndreaOsma/garaje)
- **Docker Hub:** [andreaosma/garaje](https://hub.docker.com/r/andreaosma/garaje)

---

## 📥 Descarga rápida

| | Plataforma | |
|:---:|---|---|
| 🐳 | **Docker / self-host** | `docker run --rm -p 127.0.0.1:8080:8080 -v garaje_data:/data andreaosma/garaje:latest` |

---

## Qué hace

| Sección | Qué hay |
|---------|---------|
| 🏠 **Inicio** | Tu coche por dentro en 3D (rayos X o exterior), semáforo «listo para circular», avisos, odómetro, consumo, coste por km, próximo mantenimiento y últimos datos OBD |
| 🔧 **Mecánica** | Semáforo del coche, incidencias, revisiones con checklist, plan de mantenimiento por km o meses, historial de taller y el coche en 3D (motor de 3 a 6 cilindros, frenos, suspensión, caja, turbo…) con cada pieza coloreada por sus incidencias |
| ⛽ **Repostajes** | Litros, precio y consumo real entre llenados |
| 💶 **Gastos** | Todo lo que cuesta el coche y su coste por km |
| 📄 **Documentos** | ITV, seguro, impuesto… con su caducidad y avisos |
| 🩺 **Diagnóstico** | Códigos de avería con su descripción, testigo MIL, monitores de emisiones, batería y alternador, sesiones de conducción con gráficas |
| ⚙️ **Vehículo** | Datos del coche, conexión OBD (token de ingesta) e IA |

Los códigos del fabricante (P1xxx, C1xxx…) significan cosas distintas según la marca: con IA
configurada, Garaje los investiga para *tu* coche y te dice gravedad, causas típicas y fuentes.
Si usas [Soberan](https://github.com/AndreaOsma/soberan) (finanzas personales), puede enviar a
Garaje la valoración del coche, la deuda de la financiación y los movimientos del banco de las
categorías que elijas (gasolina, taller…), que llegan a una bandeja para añadirlos como gastos.
Es Soberan quien inicia la sincronización: Garaje no guarda ninguna credencial suya.

---

<a id="self-hosted-docker"></a>
## 🐳 Self-hosted (Docker)

Una sola imagen (interfaz + API + SQLite) que escucha en el puerto **8080**.

```bash
git clone https://github.com/AndreaOsma/garaje.git garaje
cd garaje/deploy
cp .env.example .env      # opcional: puerto, zona horaria, IA del servidor…
docker compose up -d --build
```

Abre `http://127.0.0.1:8080`. Por defecto solo escucha en este equipo (`GARAJE_BIND`). Los datos
quedan en el volumen `garaje_data` (`/data/garaje.db`).

### Variables de entorno

Todas opcionales; Compose las lee de `deploy/.env` ([ejemplo](deploy/.env.example)).

| Variable | Por defecto | Para qué |
|---|---|---|
| `GARAJE_HTTP_PORT` | `8080` | Puerto en el host (solo Compose) |
| `GARAJE_BIND` | `127.0.0.1` | Interfaz donde escucha (solo Compose). `0.0.0.0` solo con un proxy con login o una VPN delante |
| `GARAJE_TZ` | `Europe/Madrid` | Zona horaria de las grabaciones de Car Scanner (vienen en hora local) |
| `GARAJE_ANTHROPIC_API_KEY` | *(vacío)* | IA del servidor para investigar códigos (Claude con búsqueda web). También se elige en *Ajustes* |
| `GARAJE_OLLAMA_URL`, `GARAJE_OLLAMA_MODEL` | *(vacío)* | Alternativa local y gratuita: tu servidor Ollama |
| `GARAJE_SECRET_KEY` | *(se genera)* | Clave Fernet para cifrar la clave de la IA guardada desde *Ajustes* |
| `SSL_CERT_FILE` | *(vacío)* | CA propia si tu Ollama va detrás de un proxy con certificado interno |

<a id="seguridad"></a>
### ⚠️ Seguridad: la app no tiene login

Garaje es **de un solo usuario y no tiene autenticación propia**. Si la expones fuera de tu red,
ponla detrás de un proxy con autenticación (Authelia, Authentik, Cloudflare Access…) o accede por
VPN (Tailscale, WireGuard). Si usas la ingesta automática del OBD, deja fuera del login solo
`/api/ingest/*`: lleva su propio token por vehículo. Más detalle en [SECURITY.md](SECURITY.md).

### Actualizar

```bash
cd garaje && git pull
cd deploy && docker compose up -d --build
```

Las migraciones de la base se aplican solas al arrancar.

---

## Automatizar el OBD

Cada vehículo tiene un **token de ingesta** (Vehículo → Conexión OBD; se guarda solo
su sha256). Dos vías, ambas idempotentes:

| Vía | Qué sube | Cómo |
|---|---|---|
| **Car Scanner (iOS/Android) + Atajo de iOS** | CSV de una grabación (lecturas en el tiempo) o TXT de un informe de diagnóstico / log del ELM327 (códigos de avería, valores, VIN) | Compartir → Atajo que hace `POST /api/ingest/file` (multipart `file`, `date`, `tz`) con `Authorization: Bearer <token>` (también vale el token a secas). El formato se detecta por el contenido. Pasos en la propia app; el iPhone tiene que llegar a tu Garaje (misma red, VPN o proxy). |
| **Agente ELM327** (`app/obd/agent.py`) | Sensores, DTC confirmados/pendientes/permanentes, monitores, VIN, `ATRV`, odómetro (PID A6) | `pip install -r backend/requirements-agent.txt` y `GARAJE_TOKEN=… python -m app.obd.agent --server https://garaje.example.com --ble auto` (o `--tcp host:35000`, `--serial /dev/rfcomm0`). Sin red guarda lotes en `~/.cache/garaje-agent` y los reenvía al reconectar. `--clear-dtc` es lo único que escribe en la ECU. |

Car Scanner exporta en formato largo (`"SECONDS";"PID";"VALUE";"UNITS"`, segundos
desde medianoche en hora local): por eso el importador necesita el día y la zona
horaria (`GARAJE_TZ`, por defecto `Europe/Madrid`). Los nombres de sensor se
mapean a PIDs estándar en inglés y español; el resto se guarda como `cs:<slug>`.

En iPhone el adaptador tiene que ser BLE o WiFi (el Bluetooth clásico no funciona en iOS).

---

## 🛠️ Desarrollo

Requisitos: Python 3.12 y Node 22.

```bash
# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080

# Frontend (otra terminal, desde la raíz)
npm install
npm run dev        # http://localhost:5173, proxea /api al backend
```

Tests:

```bash
cd backend && pytest     # API, importadores OBD, mantenimiento, IA
npm run build            # comprueba los tipos y genera dist/
```

### Stack

| Capa | Tecnología |
|---|---|
| API | FastAPI · SQLAlchemy 2 · Alembic · SQLite |
| Interfaz | React 18 · TypeScript · Vite · three.js |
| OBD | Importadores de Car Scanner (CSV/TXT) y agente ELM327 (BLE, WiFi, serie) |
| IA | Proveedor configurable, salida validada; sin IA todo lo demás funciona igual |

---

## Licencia

[MIT](LICENSE).

## Comunidad

| | |
|---|---|
| Seguridad | [SECURITY.md](SECURITY.md) — avisos privados por GitHub |

© 2026 [Andrea Osma Rafael](https://andreaosma.com)
