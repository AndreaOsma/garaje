#!/bin/sh
set -e

PORT="${PORT:-8080}"
# /data lo crea Docker como root (bind mount): dárselo al usuario app y arrancar ya sin privilegios.
if [ "$(id -u)" = "0" ]; then
  [ -d /data ] && chown -R app:app /data
  # Secretos montados de agenix (root 0400): copia dentro del contenedor que solo lee el usuario app,
  # y las variables que apuntaban a /run/secrets/… pasan a la copia.
  if [ -d /run/secrets ]; then
    install -d -o app -g app -m 0500 /run/app-secrets
    for f in /run/secrets/*; do [ -f "$f" ] && install -o app -g app -m 0400 "$f" /run/app-secrets/; done
    for v in $(env | sed -n 's|^\([A-Za-z_][A-Za-z0-9_]*\)=/run/secrets/.*|\1|p'); do
      eval "export $v=\"/run/app-secrets/\${$v#/run/secrets/}\""
    done
  fi
  exec setpriv --reuid=app --regid=app --init-groups --no-new-privs uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
