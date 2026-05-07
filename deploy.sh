#!/bin/bash

# Script de despliegue para EC2
# Uso: ./deploy.sh [environment]
# Ejemplo: ./deploy.sh production

set -e

ENVIRONMENT=${1:-production}
DEPLOY_DIR="/home/ubuntu/beauty-assistant"

echo "🚀 Iniciando despliegue en $ENVIRONMENT..."

# Crear directorio si no existe
ssh ubuntu@$SSH_HOST "mkdir -p $DEPLOY_DIR"

# Copiar archivos necesarios
echo "📦 Copiando archivos..."
scp docker-compose.yml ubuntu@$SSH_HOST:$DEPLOY_DIR/
scp .env ubuntu@$SSH_HOST:$DEPLOY_DIR/ || echo "⚠️  .env no encontrado, usando variables del servidor"

# Ejecutar despliegue
echo "🔄 Desplegando en EC2..."
ssh ubuntu@$SSH_HOST << EOF
  cd $DEPLOY_DIR
  
  # Login en GitHub Container Registry
  echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin
  
  # Descargar última imagen
  docker compose pull
  
  # Reiniciar contenedor
  docker compose up -d
  
  # Limpiar imágenes viejas
  docker image prune -f
  
  echo "✅ Despliegue completado"
EOF

echo "✨ Despliegue finalizado exitosamente"
