import mqtt from 'mqtt';
import { PrismaClient } from '@prisma/client';
import { latLngToCell } from 'h3-js';

const prisma = new PrismaClient();

interface MeshtasticMessage {
    sender: string;
    from: number;
    to: number;
    channel: number;
    id: number;
    timestamp: number;
    payload?: {
        latitude?: number;
        longitude?: number;
        altitude?: number;
        text?: string;
    };
    decoded?: {
        portnum?: number;
        payload?: string;
    };
}

class MeshtasticIngestion {
    private client: mqtt.MqttClient;

    constructor() {
        const brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://mqtt.meshtastic.org';
        this.client = mqtt.connect(brokerUrl);

        this.client.on('connect', () => {
            console.log('Connected to MQTT broker:', brokerUrl);
            this.client.subscribe('msh/+/2/json/#', (err) => {
                if (err) {
                    console.error('Subscription error:', err);
                } else {
                    console.log('Subscribed to Meshtastic topics');
                }
            });
        });

        this.client.on('message', this.handleMessage.bind(this));
        this.client.on('error', (err) => {
            console.error('MQTT error:', err);
        });
    }

    private async handleMessage(topic: string, message: Buffer) {
        try {
            const data: MeshtasticMessage = JSON.parse(message.toString());

            // Process position data
            if (data.payload?.latitude && data.payload?.longitude) {
                await this.processPosition(data);
            }

            // Process text messages for !registerme
            if (data.decoded?.payload) {
                const text = Buffer.from(data.decoded.payload, 'base64').toString('utf-8');
                if (text.trim().toLowerCase() === '!registerme') {
                    await this.registerPlayer(data);
                }
            }

            // Store raw message
            await this.storeMessage(data);

        } catch (error) {
            console.error('Error processing message:', error);
        }
    }

    private async processPosition(data: MeshtasticMessage) {
        const { latitude, longitude, altitude } = data.payload!;
        const nodeId = data.sender || data.from.toString();

        // Calculate H3 hexagon
        const hexId = latLngToCell(latitude!, longitude!, 8);

        // Upsert node
        await prisma.node.upsert({
            where: { nodeId },
            update: { lastSeen: new Date() },
            create: {
                nodeId,
                lastSeen: new Date(),
            },
        });

        // Store position
        await prisma.position.create({
            data: {
                nodeId,
                latitude: latitude!,
                longitude: longitude!,
                altitude,
                hexagonId: hexId,
                timestamp: new Date(data.timestamp * 1000),
            },
        });

        // Upsert hexagon
        await prisma.hexagon.upsert({
            where: { hexId },
            update: {
                lastSeen: new Date(),
                messageCount: { increment: 1 },
            },
            create: {
                hexId,
                resolution: 8,
                messageCount: 1,
            },
        });

        console.log(`Position stored: ${nodeId} at hex ${hexId}`);
    }

    private async registerPlayer(data: MeshtasticMessage) {
        const nodeId = data.sender || data.from.toString();

        await prisma.player.upsert({
            where: { nodeId },
            update: { lastSeen: new Date() },
            create: {
                nodeId,
                registeredAt: new Date(),
            },
        });

        console.log(`Player registered: ${nodeId}`);
    }

    private async storeMessage(data: MeshtasticMessage) {
        await prisma.message.create({
            data: {
                from: data.sender || data.from.toString(),
                to: data.to.toString(),
                channel: data.channel,
                packetId: data.id,
                portnum: data.decoded?.portnum || 0,
                timestamp: new Date(data.timestamp * 1000),
            },
        });
    }
}

// Start the ingestion service
const ingestion = new MeshtasticIngestion();

process.on('SIGINT', async () => {
    console.log('Shutting down...');
    await prisma.$disconnect();
    process.exit(0);
});
