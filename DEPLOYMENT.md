# Guía de Despliegue - Beauty Assistant

Esta guía explica cómo desplegar Beauty Assistant en un servidor EC2 de AWS usando GitHub Actions para despliegue automático.

## Arquitectura

- **Contenedor**: Docker con Python 3.11
- **Registry**: GitHub Container Registry (ghcr.io)
- **Orquestación**: Docker Compose
- **CI/CD**: GitHub Actions
- **Servidor**: AWS EC2

## Configuración Inicial

### 1. Configurar Secrets en GitHub

Ve a tu repositorio en GitHub → Settings → Secrets and variables → Actions y agrega:

| Secret | Descripción | Ejemplo |
|--------|-------------|---------|
| `SSH_HOST` | IP pública de tu instancia EC2 | `ec2-xx-xx-xx-xx.compute.amazonaws.com` |
| `SSH_USER` | Usuario de SSH en EC2 | `ubuntu` |
| `SSH_KEY` | Clave privada SSH (contenido completo de .pem) | `-----BEGIN RSA PRIVATE KEY-----...` |
| `GITHUB_TOKEN` | Token de GitHub (ya está disponible automáticamente) | - |
| `GITHUB_USERNAME` | Tu usuario de GitHub | `tu-usuario` |

### 2. Configurar el Servidor EC2

#### Instalar Docker y Docker Compose

```bash
# Conectar a EC2
ssh -i tu-clave.pem ubuntu@tu-ip-publica

# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Instalar Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin -y

# Agregar usuario al grupo docker
sudo usermod -aG docker ubuntu

# Salir y volver a entrar
exit
ssh -i tu-clave.pem ubuntu@tu-ip-publica
```

#### Crear directorio de despliegue

```bash
mkdir -p ~/beauty-assistant
cd ~/beauty-assistant
```

#### Configurar archivo .env

```bash
# Copiar tu archivo .env local
scp .env ubuntu@tu-ip-publica:~/beauty-assistant/

# O crearlo manualmente en el servidor
nano ~/beauty-assistant/.env
```

Variables requeridas en `.env`:
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
DEEPSEEK_API_KEY=tu_api_key
WHATSAPP_PHONE_NUMBER_ID=tu_phone_id
WHATSAPP_ACCESS_TOKEN=tu_access_token
WHATSAPP_VERIFY_TOKEN=tu_verify_token
```

### 3. Configurar Security Group en AWS

Asegúrate de que tu Security Group permita:
- **Puerto 22 (SSH)**: Tu IP o 0.0.0.0/0
- **Puerto 8000 (HTTP)**: 0.0.0.0/0 (o un load balancer)
- **Puerto 443 (HTTPS)**: Si usas SSL

## Flujo de Despliegue Automático

### Cómo funciona

1. Haces un push a la rama `main`
2. GitHub Actions se activa automáticamente
3. Construye la imagen Docker y la sube a GitHub Container Registry
4. Se conecta a tu EC2 por SSH
5. Descarga la nueva imagen
6. Reinicia el contenedor con `docker compose up -d`

### Workflow de GitHub Actions

El archivo `.github/workflows/deploy.yml` define:
- **Job `build-and-push`**: Construye y pushea la imagen a ghcr.io
- **Job `deploy`**: Despliega en EC2 usando SSH

## Despliegue Manual

Si necesitas hacer un despliegue manual sin GitHub Actions:

```bash
# Dar permisos al script
chmod +x deploy.sh

# Desplegar
./deploy.sh production
```

O directamente en el servidor:

```bash
ssh ubuntu@tu-ip-publica
cd ~/beauty-assistant

# Login en GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin

# Actualizar imagen y reiniciar
docker compose pull
docker compose up -d

# Ver logs
docker compose logs -f
```

## Monitoreo

### Ver logs del contenedor

```bash
ssh ubuntu@tu-ip-publica
cd ~/beauty-assistant
docker compose logs -f
```

### Ver estado del contenedor

```bash
docker compose ps
```

### Ver health check

```bash
curl http://localhost:8000/health
```

## Troubleshooting

### El contenedor no inicia

```bash
# Ver logs de error
docker compose logs app

# Verificar variables de entorno
docker compose config

# Reconstruir desde cero
docker compose down
docker compose pull
docker compose up -d
```

### Error de conexión a BD

Verifica que `DATABASE_URL` en `.env` sea correcta y accesible desde EC2.

### Error de autenticación en GitHub Container Registry

Asegúrate de que el token tenga permisos de `read:packages` y `write:packages`.

### Los cambios no se reflejan

```bash
# Forzar recreación del contenedor
docker compose up -d --force-recreate
```

## Actualizar Python version

Si necesitas cambiar la versión de Python:

1. Actualiza `Dockerfile`:
```dockerfile
FROM python:3.13-slim
```

2. Haz commit y push - el workflow reconstruirá la imagen automáticamente.

## Backup y Restore

### Backup de base de datos

```bash
# En el servidor
docker exec beauty-assistant pg_dump -U user dbname > backup.sql
```

### Restore de base de datos

```bash
# En el servidor
docker exec -i beauty-assistant psql -U user dbname < backup.sql
```

## Seguridad

- Usa HTTPS en producción (configura Nginx o un Load Balancer)
- Nunca commitees el archivo `.env`
- Rota las claves SSH regularmente
- Usa IAM roles para EC2 en lugar de credenciales hardcodeadas
- Configura firewall para restringir acceso

## Escalado

Para escalar horizontalmente:

1. Usa un Load Balancer de AWS (ALB)
2. Despliega múltiples instancias EC2
3. Configura el mismo despliegue en cada instancia
4. El Load Balancer distribuirá el tráfico

## Soporte

Para problemas de despliegue:
1. Revisa los logs de GitHub Actions
2. Revisa los logs del contenedor en EC2
3. Verifica las variables de entorno
4. Verifica la conectividad de red
