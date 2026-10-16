"""Configuración leída de variables de entorno. Sin pydantic-settings: pocas claves, ad-hoc como en Soberan."""
import os

APP_NAME = "Garaje"

# Puerto Docker/self-host (distinto del puerto fijo 17891 usado en desktop/mobile/iOS, ver desktop.py).
PORT = int(os.getenv("PORT", "8080"))

CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]

# Umbrales a partir de los cuales una tarea de mantenimiento / un vencimiento pasa a "pronto".
SOON_KM = 1000
SOON_DAYS = 30

# Límite de subida para CSV de Car Scanner (un viaje largo a 1 Hz con 30 PIDs son ~5 MB).
MAX_CSV_UPLOAD_BYTES = 20 * 1024 * 1024

# Límite de muestras por petición de ingesta (agente / Car Scanner) para no bloquear SQLite.
MAX_SAMPLES_PER_REQUEST = 200_000

# Tensión de batería (motor parado) por debajo de la cual se avisa en Inicio.
LOW_BATTERY_VOLTS = 12.2

# Zona horaria por defecto para interpretar los CSV de Car Scanner (sus tiempos son
# "segundos desde medianoche" en hora local del móvil) cuando quien sube no la indica.
DEFAULT_TZ = os.getenv("GARAJE_TZ", "Europe/Madrid")
