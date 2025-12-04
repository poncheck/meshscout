# 🐳 MeshScout Docker Setup

Complete Docker Compose setup for MeshScout - real-time Meshtastic network visualization.

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose v2.0+

## 🚀 Quick Start

### 1. Build and start all services:
```bash
docker-compose up --build
```

### 2. Initialize the database (first time only):
```bash
# In another terminal
chmod +x scripts/init-db.sh
./scripts/init-db.sh
```

### 3. Access the application:
- **Frontend**: http://localhost:3000
- **API**: http://localhost:3001
- **Database**: localhost:5432

## 🛠️ Development Commands

### Start services
```bash
# Start all services
docker-compose up

# Start in detached mode
docker-compose up -d

# Rebuild and start
docker-compose up --build
```

### Stop services
```bash
# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes database)
docker-compose down -v
```

### View logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f ingestion
docker-compose logs -f web
```

### Execute commands in containers
```bash
# Access API container shell
docker-compose exec api sh

# Run Prisma commands
docker-compose exec api npx prisma studio
docker-compose exec api npx prisma db push

# Access PostgreSQL
docker-compose exec postgres psql -U meshscout -d meshscout
```

## 📊 Services Overview

### **postgres** (Port 5432)
- PostgreSQL 16 with PostGIS extension
- Database: `meshscout`
- User: `meshscout`
- Password: `meshscout123`

### **ingestion** (Internal)
- Connects to MQTT broker
- Decodes Meshtastic packets
- Stores data in PostgreSQL

### **api** (Port 3001)
- REST API for data access
- WebSocket support
- Serves frontend data

### **web** (Port 3000)
- Next.js frontend
- 3D globe visualization
- Real-time updates

## 🗄️ Database Management

### View database contents:
```bash
docker-compose exec postgres psql -U meshscout -d meshscout -c "\dt"
```

### Check data:
```bash
# Nodes
docker-compose exec postgres psql -U meshscout -d meshscout -c "SELECT COUNT(*) FROM \"Node\";"

# Positions
docker-compose exec postgres psql -U meshscout -d meshscout -c "SELECT COUNT(*) FROM \"Position\";"

# Telemetry
docker-compose exec postgres psql -U meshscout -d meshscout -c "SELECT COUNT(*) FROM \"Telemetry\";"
```

### Backup database:
```bash
docker-compose exec postgres pg_dump -U meshscout meshscout > backup.sql
```

### Restore database:
```bash
cat backup.sql | docker-compose exec -T postgres psql -U meshscout -d meshscout
```

## 🔧 Configuration

### Environment Variables

Edit `docker-compose.yml` to change:
- Database credentials
- MQTT broker URL
- API port
- Mapbox token

### Hot Reload

Source code is mounted as volumes for hot reload:
- `apps/ingestion/src` → Auto-reload on changes
- `apps/api/src` → Auto-reload on changes
- `apps/web/src` → Auto-reload on changes

## 🐛 Troubleshooting

### Prisma client errors
```bash
# Regenerate Prisma client
docker-compose exec api npx prisma generate
docker-compose restart api ingestion
```

### Database connection issues
```bash
# Check PostgreSQL status
docker-compose exec postgres pg_isready -U meshscout

# View PostgreSQL logs
docker-compose logs postgres
```

### Port already in use
```bash
# Find and kill process using port 3000/3001
lsof -ti:3000 | xargs kill -9
lsof -ti:3001 | xargs kill -9
```

### Clean restart
```bash
# Stop everything and clean up
docker-compose down -v
docker system prune -f

# Rebuild from scratch
docker-compose up --build
```

## 📈 Production Deployment

For production, create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # Use secrets
    volumes:
      - /var/lib/meshscout/postgres:/var/lib/postgresql/data

  api:
    build:
      dockerfile: Dockerfile.api.prod
    command: ["npm", "start"]
    restart: always

  web:
    build:
      dockerfile: Dockerfile.web.prod
    command: ["npm", "start"]
    restart: always
```

Deploy with:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 🔐 Security Notes

⚠️ **IMPORTANT**: Before deploying to production:

1. Change default database password in `docker-compose.yml`
2. Use Docker secrets or environment files for sensitive data
3. Enable SSL for PostgreSQL
4. Use reverse proxy (nginx/traefik) for HTTPS
5. Limit network exposure of PostgreSQL

## 📝 Notes

- First startup may take 5-10 minutes to build images
- Prisma generates types at build time
- Database persists in Docker volume `postgres_data`
- Hot reload works for code changes
- No need to manually run `npm install`
