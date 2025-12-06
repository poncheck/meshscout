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
        const mqttOptions: any = {
            reconnectPeriod: 5000,
            encoding: 'binary', // Preserve binary data, don't convert to UTF-8
        };

        // Add credentials if provided
        if (process.env.MQTT_USERNAME) {
            mqttOptions.username = process.env.MQTT_USERNAME;
        }
        if (process.env.MQTT_PASSWORD) {
            mqttOptions.password = process.env.MQTT_PASSWORD;
        }

        this.client = mqtt.connect(brokerUrl, mqttOptions);

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
        }, 30000);
    }

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
            } catch (meshError) {
                // Try direct MeshPacket decode as fallback
                try {
                    packet = meshtastic.MeshPacket.decode(payload);
                } catch (directError) {
                    // Silently skip packets that can't be decoded (likely corrupted or unknown format)
                    return;
                }
            }
            const fromNode = packet.from?.toString() || 'unknown';
            const toNode = packet.to?.toString() || 'broadcast';

            // Try to decrypt encrypted packets using default key
            if (!packet.decoded && packet.encrypted && packet.encrypted.length > 0) {
                try {
                    console.log(`🔐 Encrypted packet from ${fromNode} (ID: ${packet.id}, size: ${packet.encrypted.length} bytes)`);
                    console.log(`🔍 Encrypted hex (first 40 bytes):`, Buffer.from(packet.encrypted).slice(0, 40).toString('hex'));

                    const decrypted = decryptMeshtasticPacket(
                        Buffer.from(packet.encrypted),
                        packet.id || 0,
                        packet.from || 0,
                        DEFAULT_KEY
                    );

                    console.log(`🔓 Decrypted ${decrypted.length} bytes`);
                    console.log(`🔍 Decrypted hex (first 40 bytes):`, decrypted.slice(0, 40).toString('hex'));

                    // Try to decode the decrypted data as a Data message
                    const data = meshtastic.Data.decode(decrypted);

                    // Replace encrypted data with decoded data
                    packet.decoded = data;

                    console.log(`✅ Successfully decrypted: portnum=${data.portnum} (${meshtastic.PortNum[data.portnum] || 'UNKNOWN'})`);
                } catch (decryptError: any) {
                    // Decryption failed - likely using a custom key we don't have
                    console.log(`⏭️  Decrypt failed for ${fromNode}: ${decryptError.message}`);
                    // Don't log every failed decrypt - most channels use custom keys
                    return;
                }
            }

            // Decode the payload based on portnum
            if (packet.decoded) {
                const portnum = packet.decoded.portnum;

                // Log all decoded packets with their portnum
                console.log(`📦 Decoded packet from ${fromNode}: portnum=${portnum} (${meshtastic.PortNum[portnum] || 'UNKNOWN'})`);

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
                            snr: packet.rxSnr,
                            rssi: packet.rxRssi,
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
                    await this.processTelemetry(fromNode, telemetry, new Date(packet.rxTime ? packet.rxTime * 1000 : Date.now()));
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
                    try {
                        const route = meshtastic.RouteDiscovery.decode(packet.decoded.payload);
                        console.log(`🛤️  Traceroute from ${fromNode} with ${route.route?.length || 0} hops`);

                        if (route.route && route.route.length > 0) {
                            // Create traceroute record
                            const traceroute = await prisma.traceroute.create({
                                data: {
                                    sourceNode: fromNode,
                                    destNode: route.route[route.route.length - 1]?.toString() || 'unknown',
                                    timestamp: new Date(packet.rxTime ? packet.rxTime * 1000 : Date.now()),
                                    verified: false, // We can verify later based on positions
                                },
                            });

                            // Create hop records
                            for (let i = 0; i < route.route.length; i++) {
                                await prisma.tracerouteHop.create({
                                    data: {
                                        tracerouteId: traceroute.id,
                                        hopNumber: i,
                                        nodeId: route.route[i].toString(),
                                        snr: route.snrTowards && route.snrTowards[i] ? route.snrTowards[i] : null,
                                    },
                                });
                            }

                            console.log(`✅ Saved traceroute ${traceroute.id} with ${route.route.length} hops`);
                        }
                    } catch (error) {
                        console.error(`Error processing TRACEROUTE from ${fromNode}:`, error);
                    }
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
            // Silently skip messages that fail to process
        }
    }

    private async processPosition(data: {
        nodeId: string;
        latitude: number;
        longitude: number;
        altitude?: number;
        timestamp: Date;
        snr?: number;
        rssi?: number;
    }) {
        const { nodeId, latitude, longitude, altitude, timestamp, snr, rssi } = data;

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
                snr,
                rssi,
            },
        });

        const snrInfo = snr !== undefined ? ` SNR: ${snr.toFixed(1)} dB` : '';
        const rssiInfo = rssi !== undefined ? ` RSSI: ${rssi} dBm` : '';
        console.log(`📍 Position: ${nodeId} at hex ${hexId} (${latitude.toFixed(4)}, ${longitude.toFixed(4)})${snrInfo}${rssiInfo}`);
    }

    private async processTelemetry(nodeId: string, telemetry: any, timestamp: Date) {
        try {
            // Ensure node exists
            await prisma.node.upsert({
                where: { nodeId },
                update: { lastSeen: timestamp },
                create: {
                    nodeId,
                    lastSeen: timestamp,
                },
            });

            const telemetryData: any = {
                nodeId,
                timestamp,
                variant: null,
            };

            // Device metrics
            if (telemetry.deviceMetrics) {
                const dm = telemetry.deviceMetrics;
                telemetryData.variant = 'device_metrics';
                telemetryData.batteryLevel = dm.batteryLevel;
                telemetryData.voltage = dm.voltage;
                telemetryData.channelUtilization = dm.channelUtilization;
                telemetryData.airUtilTx = dm.airUtilTx;
                telemetryData.uptimeSeconds = dm.uptimeSeconds;

                console.log(`📊 Device metrics from ${nodeId}: Battery ${dm.batteryLevel}%, Voltage ${dm.voltage}V, Uptime ${dm.uptimeSeconds}s`);
            }

            // Environment metrics
            if (telemetry.environmentMetrics) {
                const em = telemetry.environmentMetrics;
                telemetryData.variant = 'environment_metrics';
                telemetryData.temperature = em.temperature;
                telemetryData.relativeHumidity = em.relativeHumidity;
                telemetryData.barometricPressure = em.barometricPressure;
                telemetryData.gasResistance = em.gasResistance;
                telemetryData.iaq = em.iaq;
                telemetryData.distance = em.distance;
                telemetryData.lux = em.lux;
                telemetryData.whiteLux = em.whiteLux;
                telemetryData.ir = em.ir;
                telemetryData.uv = em.uv;
                telemetryData.windDirection = em.windDirection;
                telemetryData.windSpeed = em.windSpeed;
                telemetryData.windGust = em.windGust;
                telemetryData.windLull = em.windLull;

                console.log(`📊 Environment from ${nodeId}: Temp ${em.temperature}°C, Humidity ${em.relativeHumidity}%`);
            }

            // Power metrics
            if (telemetry.powerMetrics) {
                const pm = telemetry.powerMetrics;
                telemetryData.variant = 'power_metrics';
                telemetryData.ch1Voltage = pm.ch1Voltage;
                telemetryData.ch1Current = pm.ch1Current;
                telemetryData.ch2Voltage = pm.ch2Voltage;
                telemetryData.ch2Current = pm.ch2Current;
                telemetryData.ch3Voltage = pm.ch3Voltage;
                telemetryData.ch3Current = pm.ch3Current;

                console.log(`📊 Power metrics from ${nodeId}`);
            }

            // Air quality metrics
            if (telemetry.airQualityMetrics) {
                const aq = telemetry.airQualityMetrics;
                telemetryData.variant = 'air_quality_metrics';
                telemetryData.pm10 = aq.pm10Standard;
                telemetryData.pm25 = aq.pm25Standard;
                telemetryData.pm100 = aq.pm100Standard;

                console.log(`📊 Air quality from ${nodeId}: PM2.5 ${aq.pm25Standard}, PM10 ${aq.pm10Standard}`);
            }

            // Local stats
            if (telemetry.localStats) {
                const ls = telemetry.localStats;
                telemetryData.variant = 'local_stats';
                telemetryData.numPacketsTx = ls.numPacketsTx;
                telemetryData.numPacketsRx = ls.numPacketsRx;
                telemetryData.numPacketsRxBad = ls.numPacketsRxBad;
                telemetryData.numOnlineNodes = ls.numOnlineNodes;
                telemetryData.numTotalNodes = ls.numTotalNodes;

                console.log(`📊 Local stats from ${nodeId}: TX ${ls.numPacketsTx}, RX ${ls.numPacketsRx}, Online nodes ${ls.numOnlineNodes}`);
            }

            // Health metrics
            if (telemetry.healthMetrics) {
                const hm = telemetry.healthMetrics;
                telemetryData.variant = 'health_metrics';
                telemetryData.heartBpm = hm.heartBpm;
                telemetryData.spO2 = hm.spO2;
                telemetryData.bodyTempC = hm.bodyTempC;

                console.log(`📊 Health metrics from ${nodeId}: Heart ${hm.heartBpm} BPM, SpO2 ${hm.spO2}%`);
            }

            // Store telemetry in database
            await prisma.telemetry.create({
                data: telemetryData,
            });

            console.log(`✅ Stored ${telemetryData.variant} telemetry from ${nodeId}`);
        } catch (error) {
            console.error(`❌ Error processing telemetry from ${nodeId}:`, error);
        }
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
