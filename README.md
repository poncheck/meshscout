# MeshScout

A real-time visualization service for the Meshtastic network, displaying node coverage using H3 hexagons and gamifying network exploration.

## Project Structure

```
meshscout/
├── apps/
│   ├── web/          # Next.js frontend
│   ├── api/          # Express API server
│   └── ingestion/    # MQTT ingestion service
└── packages/
    └── shared/       # Shared Prisma schema
```

## Getting Started

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Setup database**:
   ```bash
   cp .env.example .env
   # Edit .env with your PostgreSQL connection string
   cd packages/shared
   npm run db:push
   ```

3. **Run development servers**:
   ```bash
   npm run dev
   ```

## Features

- **Real-time MQTT ingestion** from Meshtastic network
- **H3 hexagon visualization** (resolution 8) showing network coverage
- **Traceroute tracking** for network path analysis
- **Gamification system** - earn points for verified traceroutes (1 point per km)
- **Player registration** via `!registerme` command on public channels

## Tech Stack

- **Frontend**: Next.js, TypeScript, TailwindCSS, MapLibre GL JS
- **Backend**: Node.js, Express, WebSockets
- **Database**: PostgreSQL with PostGIS
- **Ingestion**: MQTT.js, Protobuf
- **Mapping**: H3 (Uber's Hexagonal Hierarchical Spatial Index)
