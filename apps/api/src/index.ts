import express from 'express';
import cors from 'cors';
import { WebSocketServer } from 'ws';
import { PrismaClient } from '@prisma/client';
import { cellToBoundary, gridDisk } from 'h3-js';
import http from 'http';

const app = express();
const prisma = new PrismaClient();
const PORT = Number(process.env.API_PORT || 3001);

app.use(cors());
app.use(express.json());

// Get active hexagons
app.get('/api/hexagons', async (req, res) => {
    try {
        const { limit = 1000 } = req.query;

        const hexagons = await prisma.hexagon.findMany({
            take: Number(limit),
            orderBy: { lastSeen: 'desc' },
            select: {
                hexId: true,
                messageCount: true,
                lastSeen: true,
            },
        });

        // Add boundaries for each hexagon
        const hexagonsWithBoundaries = hexagons.map(hex => ({
            ...hex,
            boundary: cellToBoundary(hex.hexId),
        }));

        res.json(hexagonsWithBoundaries);
    } catch (error) {
        console.error('Error fetching hexagons:', error);
        res.status(500).json({ error: 'Failed to fetch hexagons' });
    }
});

// Get hexagon details
app.get('/api/hexagons/:hexId', async (req, res) => {
    try {
        const { hexId } = req.params;

        const hexagon = await prisma.hexagon.findUnique({
            where: { hexId },
            include: {
                positions: {
                    take: 100,
                    orderBy: { timestamp: 'desc' },
                    include: {
                        node: true,
                    },
                },
            },
        });

        if (!hexagon) {
            return res.status(404).json({ error: 'Hexagon not found' });
        }

        res.json({
            ...hexagon,
            boundary: cellToBoundary(hexId),
        });
    } catch (error) {
        console.error('Error fetching hexagon:', error);
        res.status(500).json({ error: 'Failed to fetch hexagon' });
    }
});

// Get leaderboard
app.get('/api/leaderboard', async (req, res) => {
    try {
        const { limit = 100 } = req.query;

        const players = await prisma.player.findMany({
            take: Number(limit),
            orderBy: { points: 'desc' },
            select: {
                id: true,
                nodeId: true,
                longName: true,
                shortName: true,
                points: true,
                registeredAt: true,
            },
        });

        res.json(players);
    } catch (error) {
        console.error('Error fetching leaderboard:', error);
        res.status(500).json({ error: 'Failed to fetch leaderboard' });
    }
});

// Get player details
app.get('/api/players/:nodeId', async (req, res) => {
    try {
        const { nodeId } = req.params;

        const player = await prisma.player.findUnique({
            where: { nodeId },
            include: {
                traceroutes: {
                    take: 50,
                    orderBy: { timestamp: 'desc' },
                    include: {
                        hops: {
                            orderBy: { hopNumber: 'asc' },
                        },
                    },
                },
            },
        });

        if (!player) {
            return res.status(404).json({ error: 'Player not found' });
        }

        res.json(player);
    } catch (error) {
        console.error('Error fetching player:', error);
        res.status(500).json({ error: 'Failed to fetch player' });
    }
});

// Get recent positions
app.get('/api/positions', async (req, res) => {
    try {
        const { limit = 100 } = req.query;

        const positions = await prisma.position.findMany({
            take: Number(limit),
            orderBy: { timestamp: 'desc' },
            include: {
                node: true,
            },
        });

        res.json(positions);
    } catch (error) {
        console.error('Error fetching positions:', error);
        res.status(500).json({ error: 'Failed to fetch positions' });
    }
});

// Get node details with telemetry and traceroutes
app.get('/api/nodes/:nodeId', async (req, res) => {
    try {
        const { nodeId } = req.params;

        const node = await prisma.node.findUnique({
            where: { nodeId },
            include: {
                positions: {
                    take: 100,
                    orderBy: { timestamp: 'desc' },
                },
                telemetry: {
                    take: 100,
                    orderBy: { timestamp: 'desc' },
                },
            },
        });

        if (!node) {
            return res.status(404).json({ error: 'Node not found' });
        }

        // Fetch traceroutes initiated by this node
        const traceroutes = await prisma.traceroute.findMany({
            where: { sourceNode: nodeId },
            take: 20,
            orderBy: { timestamp: 'desc' },
            include: {
                hops: {
                    orderBy: { hopNumber: 'asc' },
                },
            },
        });

        // Enrich traceroutes with node names
        const enrichedTraceroutes = await Promise.all(
            traceroutes.map(async (tr) => {
                // Get destination node name
                const destNodeInfo = await prisma.node.findUnique({
                    where: { nodeId: tr.destNode },
                    select: { longName: true, shortName: true },
                });

                // Get node names for each hop
                const enrichedHops = await Promise.all(
                    tr.hops.map(async (hop) => {
                        const hopNodeInfo = await prisma.node.findUnique({
                            where: { nodeId: hop.nodeId },
                            select: { longName: true, shortName: true },
                        });
                        return {
                            ...hop,
                            nodeName: hopNodeInfo?.longName || hopNodeInfo?.shortName || hop.nodeId.slice(0, 8),
                        };
                    })
                );

                return {
                    ...tr,
                    destNodeName: destNodeInfo?.longName || destNodeInfo?.shortName || tr.destNode.slice(0, 8),
                    hops: enrichedHops,
                };
            })
        );

        res.json({
            ...node,
            traceroutes: enrichedTraceroutes,
        });
    } catch (error) {
        console.error('Error fetching node details:', error);
        res.status(500).json({ error: 'Failed to fetch node details' });
    }
});

// Get telemetry data
app.get('/api/telemetry', async (req, res) => {
    try {
        const { nodeId, variant, limit = 100 } = req.query;

        const where: any = {};
        if (nodeId) where.nodeId = nodeId as string;
        if (variant) where.variant = variant as string;

        const telemetry = await prisma.telemetry.findMany({
            where,
            take: Number(limit),
            orderBy: { timestamp: 'desc' },
            include: {
                node: true,
            },
        });

        res.json(telemetry);
    } catch (error) {
        console.error('Error fetching telemetry:', error);
        res.status(500).json({ error: 'Failed to fetch telemetry' });
    }
});

// Get latest telemetry for a node
app.get('/api/nodes/:nodeId/telemetry/latest', async (req, res) => {
    try {
        const { nodeId } = req.params;

        const latestTelemetry = await prisma.telemetry.findFirst({
            where: { nodeId },
            orderBy: { timestamp: 'desc' },
        });

        if (!latestTelemetry) {
            return res.status(404).json({ error: 'No telemetry found for this node' });
        }

        res.json(latestTelemetry);
    } catch (error) {
        console.error('Error fetching latest telemetry:', error);
        res.status(500).json({ error: 'Failed to fetch latest telemetry' });
    }
});

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Create HTTP server
const server = http.createServer(app);

// WebSocket server for real-time updates
const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
    console.log('WebSocket client connected');

    ws.on('close', () => {
        console.log('WebSocket client disconnected');
    });
});

// Broadcast function for real-time updates
export function broadcastUpdate(type: string, data: any) {
    wss.clients.forEach((client) => {
        if (client.readyState === 1) { // OPEN
            client.send(JSON.stringify({ type, data }));
        }
    });
}

server.listen(PORT, '0.0.0.0', () => {
    console.log(`API server running on http://0.0.0.0:${PORT}`);
});

process.on('SIGINT', async () => {
    console.log('Shutting down...');
    await prisma.$disconnect();
    server.close();
    process.exit(0);
});
