import { PrismaClient } from '@prisma/client';
import { getDistance } from 'geolib';

const prisma = new PrismaClient();

interface TracerouteData {
    sourceNode: string;
    destNode: string;
    hops: Array<{
        nodeId: string;
        snr?: number;
    }>;
}

export class GamificationEngine {
    /**
     * Process a traceroute and award points if verified
     */
    async processTraceroute(data: TracerouteData): Promise<void> {
        try {
            // Get player if registered
            const player = await prisma.player.findUnique({
                where: { nodeId: data.sourceNode },
            });

            // Get positions for source and destination
            const sourcePosition = await prisma.position.findFirst({
                where: { nodeId: data.sourceNode },
                orderBy: { timestamp: 'desc' },
            });

            const destPosition = await prisma.position.findFirst({
                where: { nodeId: data.destNode },
                orderBy: { timestamp: 'desc' },
            });

            // Calculate distance if both positions exist
            let distance: number | null = null;
            let verified = false;

            if (sourcePosition && destPosition) {
                distance = getDistance(
                    { latitude: sourcePosition.latitude, longitude: sourcePosition.longitude },
                    { latitude: destPosition.latitude, longitude: destPosition.longitude }
                ) / 1000; // Convert to km

                // Verify if distance is reasonable (between 0.1km and 1000km)
                verified = distance > 0.1 && distance < 1000;
            }

            // Calculate points (1 point per km)
            const points = verified && distance ? Math.floor(distance) : 0;

            // Create traceroute record
            const traceroute = await prisma.traceroute.create({
                data: {
                    playerId: player?.id,
                    sourceNode: data.sourceNode,
                    destNode: data.destNode,
                    verified,
                    distance,
                    points,
                },
            });

            // Create hop records
            for (let i = 0; i < data.hops.length; i++) {
                const hop = data.hops[i];

                // Get position for this hop to determine hexagon
                const hopPosition = await prisma.position.findFirst({
                    where: { nodeId: hop.nodeId },
                    orderBy: { timestamp: 'desc' },
                });

                await prisma.tracerouteHop.create({
                    data: {
                        tracerouteId: traceroute.id,
                        hopNumber: i,
                        nodeId: hop.nodeId,
                        hexagonId: hopPosition?.hexagonId,
                        snr: hop.snr,
                    },
                });
            }

            // Award points to player if verified
            if (verified && player && points > 0) {
                await prisma.player.update({
                    where: { id: player.id },
                    data: {
                        points: { increment: points },
                        lastSeen: new Date(),
                    },
                });

                console.log(`✅ Awarded ${points} points to ${data.sourceNode} for ${distance?.toFixed(2)}km traceroute`);
            }

        } catch (error) {
            console.error('Error processing traceroute:', error);
        }
    }

    /**
     * Recalculate points for all players (for maintenance/corrections)
     */
    async recalculateAllPoints(): Promise<void> {
        const players = await prisma.player.findMany();

        for (const player of players) {
            const traceroutes = await prisma.traceroute.findMany({
                where: {
                    playerId: player.id,
                    verified: true,
                },
            });

            const totalPoints = traceroutes.reduce((sum, tr) => sum + tr.points, 0);

            await prisma.player.update({
                where: { id: player.id },
                data: { points: totalPoints },
            });

            console.log(`Recalculated points for ${player.nodeId}: ${totalPoints}`);
        }
    }
}

export const gamificationEngine = new GamificationEngine();
