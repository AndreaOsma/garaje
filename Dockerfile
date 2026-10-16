# Stage 1: build frontend
FROM node:22-alpine AS build-frontend
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: runtime
FROM python:3.12-slim
WORKDIR /app

# Paquetes del sistema al día (parches de seguridad de Debian) — la imagen base
# no siempre trae las últimas revisiones de util-linux/bsdutils/etc.
# SECURITY_REFRESH (el CI pasa la fecha) invalida esta capa a diario: en un daemon de
# Docker compartido se reutilizaría un upgrade cacheado de otra app, ya viejo.
ARG SECURITY_REFRESH=0
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY backend/startup.sh .
RUN chmod +x startup.sh

COPY --from=build-frontend /app/dist ./static
ENV GARAJE_STATIC_DIR=/app/static

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

CMD ["./startup.sh"]
