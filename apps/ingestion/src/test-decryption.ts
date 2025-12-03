import { createCipheriv, createDecipheriv } from 'crypto';
import * as protobuf from './generated/meshtastic';

// Extract meshtastic namespace
const meshtastic = (protobuf as any).meshtastic;

// Default key: 0x01 + 31 zeros
const DEFAULT_KEY = Buffer.alloc(32);
DEFAULT_KEY[0] = 0x01;

function getNonce(packetId: number, fromNode: number): Buffer {
    // Construct nonce: packetId (8 bytes) + fromNode (4 bytes) + padding (4 bytes) = 16 bytes
    const nonce = Buffer.alloc(16);
    nonce.writeBigUInt64LE(BigInt(packetId), 0);
    nonce.writeUInt32LE(fromNode >>> 0, 8);
    return nonce;
}

function encrypt(payload: Buffer, packetId: number, fromNode: number, key: Buffer): Buffer {
    const nonce = getNonce(packetId, fromNode);
    const cipher = createCipheriv('aes-256-ctr', key, nonce);
    return Buffer.concat([cipher.update(payload), cipher.final()]);
}

function decrypt(encrypted: Buffer, packetId: number, fromNode: number, key: Buffer): Buffer {
    const nonce = getNonce(packetId, fromNode);
    const decipher = createDecipheriv('aes-256-ctr', key, nonce);
    return Buffer.concat([decipher.update(encrypted), decipher.final()]);
}

async function runTest() {
    console.log('🧪 Starting Decryption Test...');

    // 1. Create a sample Data payload (e.g., a text message)
    const text = "Hello Meshtastic!";
    const data = meshtastic.Data.create({
        portnum: meshtastic.PortNum.TEXT_MESSAGE_APP,
        payload: Buffer.from(text, 'utf8')
    });
    const payload = meshtastic.Data.encode(data).finish() as Buffer;

    console.log(`📝 Original Text: "${text}"`);
    console.log(`📦 Encoded Payload (hex): ${payload.toString('hex')}`);

    // 2. Simulate packet parameters
    const packetId = 123456789;
    const fromNode = 0x12345678; // Random node ID

    console.log(`🔢 Packet ID: ${packetId}`);
    console.log(`👤 From Node: ${fromNode.toString(16)}`);

    // 3. Encrypt
    const encrypted = encrypt(payload, packetId, fromNode, DEFAULT_KEY);
    console.log(`🔒 Encrypted (hex): ${encrypted.toString('hex')}`);

    // 4. Decrypt
    const decrypted = decrypt(encrypted, packetId, fromNode, DEFAULT_KEY);
    console.log(`🔓 Decrypted (hex): ${decrypted.toString('hex')}`);

    // 5. Verify
    if (decrypted.equals(payload)) {
        console.log('✅ SUCCESS: Decrypted payload matches original!');

        // Decode back to object
        const decodedData = meshtastic.Data.decode(decrypted);
        const decodedText = decodedData.payload.toString('utf8');
        console.log(`📝 Decoded Text: "${decodedText}"`);

        if (decodedText === text) {
            console.log('✅ SUCCESS: Text content matches!');
        } else {
            console.error('❌ FAILURE: Text content mismatch!');
        }
    } else {
        console.error('❌ FAILURE: Decrypted payload does NOT match original!');
    }
}

runTest().catch(console.error);
