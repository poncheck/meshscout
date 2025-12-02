import mqtt from 'mqtt';
import { PrismaClient } from '@prisma/client';
import { latLngToCell } from 'h3-js';
import * as meshtastic from './generated/meshtastic';
import path from 'path';
import dotenv from 'dotenv';

// Load .env from root directory
dotenv.config({ path: path.resolve(__dirname, '../../../.env') });

const prisma = new PrismaClient();

class MeshtasticIngestion {
    private client: mqtt.MqttClient;
    private messageCount = 0;
    private startTime = Date.now();

    constructor() {
        const brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://mqtt.meshtastic.org';
        this.client = mqtt.connect(brokerUrl, {
            username: 'meshdev',
            password: 'large4cats',
            reconnectPeriod: 5000,
        });

        this.client.on('connect', () => {
            console.log('✅ Connected to MQTT broker:', brokerUrl);

            // Subscribe to both JSON and protobuf topics
            const topics = [
                'msh/+/2/json/#',  // JSON messages
                'msh/+/2/e/#',     // Encrypted protobuf
                'msh/+/2/c/#',     // Compressed protobuf
            ];

            topics.forEach(topic => {
                this.client.subscribe(topic, (err) => {
                    if (err) {
                        console.error(`❌ Subscription error for ${topic}:`, err);
                    } else {
                        console.log(`📡 Subscribed to ${topic}`);
                    }
                });
            });
        });

        this.client.on('message', this.handleMessage.bind(this));
        this.client.on('error', (err) => {
            console.error('❌ MQTT error:', err);
        });

        // Log stats every 30 seconds
        setInterval(() => {
            const elapsed = (Date.now() - this.startTime) / 1000;
            const rate = (this.messageCount / elapsed).toFixed(2);
            console.log(`📊 Stats: ${this.messageCount} messages, ${rate} msg/s`);
        }, 30000);
    }

    private async handleMessage(topic: string, payload: Buffer) {
        this.messageCount++;

        try {
            // Determine if JSON or Protobuf based on topic
            if (topic.includes('/json/')) {
                await this.handleJsonMessage(payload);
            } else {
                await this.handleProtobufMessage(payload);
            }
        } catch (error) {
            console.error('❌ Error processing message:', error);
        }
    }

    private async handleJsonMessage(payload: Buffer) {
        try {
            const data = JSON.parse(payload.toString());

            // Process position data
            if (data.payload?.latitude && data.payload?.longitude) {
                await this.processPosition({
                    nodeId: data.sender || data.from?.toString(),
                    latitude: data.payload.latitude,
                    longitude: data.payload.longitude,
                    altitude: data.payload.altitude,
                    timestamp: data.timestamp ? new Date(data.timestamp * 1000) : new Date(),
                });
            }

            // Process text messages for !registerme
            if (data.decoded?.payload) {
                const text = Buffer.from(data.decoded.payload, 'base64').toString('utf-8');
                if (text.trim().toLowerCase() === '!registerme') {
                    await this.registerPlayer(data.sender || data.from?.toString());
                }
            }

            // Store raw message
            await this.storeMessage({
                from: data.sender || data.from?.toString(),
                to: data.to?.toString() || 'broadcast',
                channel: data.channel || 0,
                packetId: data.id || 0,
                portnum: data.decoded?.portnum || 0,
                timestamp: data.timestamp ? new Date(data.timestamp * 1000) : new Date(),
            });

        } catch (error) {
            console.error('Error processing JSON message:', error);
        }
    }

    private async handleProtobufMessage(payload: Buffer) {
        try {
            // Decode ServiceEnvelope
            const envelope = meshtastic.ServiceEnvelope.decode(payload);

            if (!envelope.packet) {
                return;
            }

            const packet = envelope.packet;
            const fromNode = packet.from?.toString() || 'unknown';
            const toNode = packet.to?.toString() || 'broadcast';

            // Decode the payload based on portnum
            if (packet.decoded) {
                const portnum = packet.decoded.portnum;

                // POSITION_APP
                if (portnum === meshtastic.PortNum.POSITION_APP && packet.decoded.payload) {
                    const position = meshtastic.Position.decode(packet.decoded.payload);

                    if (position.latitudeI && position.longitudeI) {
                        await this.processPosition({
                            nodeId: fromNode,
                            latitude: position.latitudeI * 1e-7,
                            longitude: position.longitudeI * 1e-7,
                            altitude: position.altitude,
                            timestamp: new Date(packet.rxTime ? packet.rxTime * 1000 : Date.now()),
                        });
                    }
                }

                // TEXT_MESSAGE_APP
                if (portnum === meshtastic.PortNum.TEXT_MESSAGE_APP && packet.decoded.payload) {
                    const text = packet.decoded.payload.toString('utf-8');

                    if (text.trim().toLowerCase() === '!registerme') {
                        await this.registerPlayer(fromNode);
                    }
                }

                // TELEMETRY_APP
                if (portnum === meshtastic.PortNum.TELEMETRY_APP && packet.decoded.payload) {
                    const telemetry = meshtastic.Telemetry.decode(packet.decoded.payload);
                    console.log(`📊 Telemetry from ${fromNode}:`, telemetry);
                }

                // TRACEROUTE_APP
                if (portnum === meshtastic.PortNum.TRACEROUTE_APP && packet.decoded.payload) {
                    const route = meshtastic.RouteDiscovery.decode(packet.decoded.payload);
                    console.log(`🛤️  Traceroute from ${fromNode}:`, route);

                    // TODO: Process traceroute for gamification
                }
            }

            // Store raw message
            await this.storeMessage({
                from: fromNode,
                to: toNode,
                channel: packet.channel || 0,
                packetId: packet.id || 0,
                portnum: packet.decoded?.portnum || 0,
                timestamp: new Date(packet.rxTime ? packet.rxTime * 1000 : Date.now()),
            });

        } catch (error) {
            console.error('Error processing Protobuf message:', error);
        }
    }

    private async processPosition(data: {
        nodeId: string;
        latitude: number;
        longitude: number;
        altitude?: number;
        timestamp: Date;
    }) {
        const { nodeId, latitude, longitude, altitude, timestamp } = data;

        // Calculate H3 hexagon
        const hexId = latLngToCell(latitude, longitude, 8);

        // Upsert node
        await prisma.node.upsert({
            where: { nodeId },
            update: { lastSeen: timestamp },
            create: {
                nodeId,
                lastSeen: timestamp,
            },
        });

        // Store position
        await prisma.position.create({
            data: {
                nodeId,
                latitude,
                longitude,
                altitude,
                hexagonId: hexId,
                timestamp,
            },
        });

        // Upsert hexagon
        await prisma.hexagon.upsert({
            where: { hexId },
            update: {
                lastSeen: timestamp,
                messageCount: { increment: 1 },
            },
            create: {
                hexId,
                resolution: 8,
                messageCount: 1,
                firstSeen: timestamp,
                lastSeen: timestamp,
            },
        });

        console.log(`📍 Position: ${nodeId} at hex ${hexId} (${latitude.toFixed(4)}, ${longitude.toFixed(4)})`);
    }

    private async registerPlayer(nodeId: string) {
        await prisma.player.upsert({
            where: { nodeId },
            update: { lastSeen: new Date() },
            create: {
                nodeId,
                registeredAt: new Date(),
            },
        });

        console.log(`🎮 Player registered: ${nodeId}`);
    }

    private async storeMessage(data: {
        from: string;
        to: string;
        channel: number;
        packetId: number;
        portnum: number;
        timestamp: Date;
    }) {
        await prisma.message.create({
            data: {
                from: data.from,
                to: data.to,
                channel: data.channel,
                packetId: data.packetId,
                portnum: data.portnum,
                timestamp: data.timestamp,
            },
        });
    }
}

// Start the ingestion service
const ingestion = new MeshtasticIngestion();

process.on('SIGINT', async () => {
    console.log('🛑 Shutting down...');
    await prisma.$disconnect();
    process.exit(0);
});
