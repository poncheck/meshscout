#!/bin/bash

echo "🚀 Setting up MeshScout..."

# Check if PostgreSQL is running
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL is not installed. Please install PostgreSQL first."
    exit 1
fi

# Copy environment file
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your database credentials"
fi

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Generate Prisma client
echo "🔧 Generating Prisma client..."
cd packages/shared
npm run db:generate

# Push database schema
echo "🗄️  Setting up database..."
npm run db:push

cd ../..

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your PostgreSQL connection string"
echo "2. Run 'npm run dev' to start all services"
echo "3. Open http://localhost:3000 in your browser"
echo ""
echo "Services:"
echo "  - Frontend: http://localhost:3000"
echo "  - API: http://localhost:3001"
echo "  - Ingestion: Running in background"
