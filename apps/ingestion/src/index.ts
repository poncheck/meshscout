import mqtt from 'mqtt';
import { PrismaClient } from '@prisma/client';
import { latLngToCell } from 'h3-js';
import * as protobuf from './generated/meshtastic';
import path from 'path';
import dotenv from 'dotenv';
import { createDecipheriv } from 'crypto';

// Extract the meshtastic namespace from the protobuf root
const meshtastic = (protobuf as any).meshtastic;

// Meshtastic default channel key "AQ==" (base64) = 0x01
// For AES256, we need to expand this to 32 bytes
const DEFAULT_KEY = Buffer.alloc(32);
DEFAULT_KEY[0] = 0x01;

/**
 * Decrypt Meshtastic packet using AES256-CTR
 * @param encryptedPayload - The encrypted payload buffer
 * @param packetId - Packet ID (used in nonce)
 * @param fromNode - Sender node number (used in nonce)
 * @param key - AES256 key (32 bytes)
 * @returns Decrypted buffer
 */
function decryptMeshtasticPacket(
    encryptedPayload: Buffer,
    packetId: number,
    fromNode: number,
    key: Buffer = DEFAULT_KEY
): Buffer {
    // Construct nonce: packetId (8 bytes) + fromNode (4 bytes) + padding (4 bytes) = 16 bytes
    // Meshtastic uses 96-bit nonce: packetId (64-bit) + fromNode (32-bit)
    const nonce = Buffer.alloc(16);

    // Write packetId as 64-bit little-endian (8 bytes)
    nonce.writeBigUInt64LE(BigInt(packetId), 0);

    // Write fromNode as 32-bit little-endian (4 bytes)
    nonce.writeUInt32LE(fromNode >>> 0, 8);

    // Remaining 4 bytes are zero (padding for AES block size)

    // Create decipher
    const decipher = createDecipheriv('aes-256-ctr', key, nonce);

    // Decrypt
    const decrypted = Buffer.concat([
        decipher.update(encryptedPayload),
        decipher.final()
    ]);

    return decrypted;
}

// Load .env from root directory
const envPath = path.resolve(__dirname, '../../../.env');
const prisma = new PrismaClient();

class MeshtasticIngestion {
    private client: mqtt.MqttClient;
    private messageCount = 0;
    private startTime = Date.now();

    constructor() {
        // Load .env from root directory
        const envPath = path.resolve(__dirname, '../../../.env');
        const result = dotenv.config({ path: envPath, override: true });

        console.log('🔍 Loading .env from:', envPath);
        if (result.error) {
            console.error('❌ Error loading .env:', result.error);
        } else {
            console.log('✅ .env loaded successfully');
            console.log('🔍 Dotenv parsed:', result.parsed);
        }

        console.log('🔍 MQTT_BROKER_URL:', process.env.MQTT_BROKER_URL);

        const brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://mqtt.meshtastic.org';
        this.client = mqtt.connect(brokerUrl, {
            username: 'meshdev',
            password: 'large4cats',
            reconnectPeriod: 5000,
            encoding: 'binary', // Preserve binary data, don't convert to UTF-8
        });

        this.client.on('connect', () => {
            console.log('✅ Connected to MQTT broker:', brokerUrl);

            // Subscribe to topics
            const topics = process.env.MQTT_TOPIC
                ? [process.env.MQTT_TOPIC]
                : [
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
            console.log(`   🔓 Decryption: ${this.decryptedCount || 0} successes, ${this.encryptedCount || 0} encrypted total`);
        }, 30000);
    }

    // Add counters
    private decryptedCount = 0;
    private encryptedCount = 0;

    private async handleMessage(topic: string, payload: Buffer) {
        this.messageCount++;

        try {
            // Filter out problematic topics
            if (topic.includes('/Deutsch/')) {
                return;
            }

            // Ensure payload is a Buffer (not corrupted by UTF-8 conversion)
            const binaryPayload = Buffer.isBuffer(payload) ? payload : Buffer.from(payload, 'binary');

            // Check if data is corrupted by UTF-8 conversion (contains replacement character)
            const hexString = binaryPayload.slice(0, 50).toString('hex');
            if (hexString.includes('efbfbd')) {
                console.warn(`⚠️  Skipping corrupted message from ${topic} - data was converted to UTF-8 by broker`);
                console.warn(`💡 Tip: Check your MQTT broker configuration or use mqtt://mqtt.meshtastic.org`);
                return;
            }

            console.log(`📨 Received message on topic: ${topic}`);
            console.log(`📦 Payload length: ${binaryPayload.length} bytes`);
            console.log(`📦 Is Buffer: ${Buffer.isBuffer(binaryPayload)}`);
            console.log(`🔍 First 50 bytes (hex):`, binaryPayload.slice(0, 50).toString('hex'));
            console.log(`🔍 First 100 chars (string):`, binaryPayload.slice(0, 100).toString('utf8'));

            // Try to detect format
            // First, try JSON
            try {
                const jsonData = JSON.parse(binaryPayload.toString());
                console.log('✅ Detected JSON format');
                await this.handleJsonMessage(binaryPayload);
                return;
            } catch {
                // Not JSON, continue
            }

            // Determine if JSON or Protobuf based on topic
            if (topic.includes('/json/')) {
                await this.handleJsonMessage(binaryPayload);
            } else {
                console.log('🔄 Attempting Protobuf decode...');
                await this.handleProtobufMessage(binaryPayload);
            }
        } catch (error) {
            console.error('❌ Error processing message:', error);
        }
    }

    private async handleJsonMessage(payload: Buffer) {
        try {
            const data = JSON.parse(payload.toString());

            // Skip unencoded messages (user requested to discard them)
            if (!data.decoded) {
                console.log('⏭️  Skipping unencoded JSON message');
                return;
            }

            const fromNode = data.sender || data.from?.toString() || 'unknown';

            // Process position data
            if (data.payload?.latitude && data.payload?.longitude) {
                await this.processPosition({
                    nodeId: fromNode,
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
                    await this.registerPlayer(fromNode);
                }
            }

            // Store raw message
            await this.storeMessage({
                from: fromNode,
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
            let packet: any;

            // Try to decode as ServiceEnvelope first
            try {
                const envelope = meshtastic.ServiceEnvelope.decode(payload);
                if (!envelope.packet) {
                    return;
                }
                packet = envelope.packet;
            } catch (envelopeError) {
                // If ServiceEnvelope decode fails, try direct MeshPacket decode
                console.log('⚠️  ServiceEnvelope decode failed, trying direct MeshPacket decode...');
                try {
                    packet = meshtastic.MeshPacket.decode(payload);
                } catch (meshPacketError) {
                    console.error('❌ Both ServiceEnvelope and MeshPacket decode failed');
                    throw meshPacketError;
                }
            }
            const fromNode = packet.from?.toString() || 'unknown';
            const toNode = packet.to?.toString() || 'broadcast';

            // Handle encryption - if packet has no decoded field but has payload, it's encrypted
            // This is because MQTT packets from /e/ topics have encrypted payload but don't set encrypted=true
            if (!packet.decoded && packet.payload && packet.payload.length > 0) {
                this.encryptedCount++;
                console.log(`🔐 Encrypted packet detected: from=${fromNode}, id=${packet.id}, payloadSize=${packet.payload.length}`);
                try {
                    const decryptedPayload = decryptMeshtasticPacket(
                        packet.payload as Buffer,
                        Number(packet.id || 0),
                        packet.from
                    );

                    // Decode the decrypted payload
                    packet.decoded = meshtastic.Data.decode(decryptedPayload);
                    this.decryptedCount++;
                    console.log(`✅ Successfully decrypted packet from ${fromNode}, portnum: ${packet.decoded.portnum} (${meshtastic.PortNum[packet.decoded.portnum]})`);
                } catch (err) {
                    console.error(`❌ Failed to decrypt packet from ${fromNode}:`, err instanceof Error ? err.message : err);
                    return; // Skip if decryption fails
                }
            }

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

                // NODEINFO_APP - Extract device names
                if (portnum === meshtastic.PortNum.NODEINFO_APP && packet.decoded.payload) {
                    try {
                        const user = meshtastic.User.decode(packet.decoded.payload);

                        if (user.longName || user.shortName) {
                            console.log(`👤 Node info from ${fromNode}: ${user.longName} (${user.shortName})`);

                            // Update node with names
                            await prisma.node.upsert({
                                where: { nodeId: fromNode },
                                update: {
                                    longName: user.longName || undefined,
                                    shortName: user.shortName || undefined,
                                    lastSeen: new Date(packet.rxTime ? packet.rxTime * 1000 : Date.now()),
                                },
                                create: {
                                    nodeId: fromNode,
                                    longName: user.longName || undefined,
                                    shortName: user.shortName || undefined,
                                    lastSeen: new Date(packet.rxTime ? packet.rxTime * 1000 : Date.now()),
                                },
                            });
                        }
                    } catch (error) {
                        console.error(`Error processing NODEINFO from ${fromNode}:`, error);
                    }
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

        // Upsert hexagon FIRST (before creating position with foreign key)
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

        // Store position (now hexagon exists)
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
