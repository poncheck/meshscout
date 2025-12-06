#!/bin/bash
set -e

echo "🔧 Initializing MeshScout database..."

# Wait for PostgreSQL to be ready
until docker compose exec -T postgres pg_isready -U meshscout; do
  echo "⏳ Waiting for PostgreSQL..."
  sleep 2
done

echo "✅ PostgreSQL is ready!"

# Apply Prisma migrations
echo "📦 Applying database schema..."
docker compose exec -T api sh -c "cd /app/packages/shared && npx prisma db push --skip-generate"

echo "✅ Database initialized successfully!"
