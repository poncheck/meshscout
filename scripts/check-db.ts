// @ts-ignore
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function checkDatabase() {
    console.log('🔍 Sprawdzam bazę danych...\n');

    try {
        // 1. Ostatnie pozycje
        console.log('📍 === OSTATNIE 20 POZYCJI ===');
        const positions = await prisma.position.findMany({
            take: 20,
            orderBy: { timestamp: 'desc' },
            include: { node: true },
        });

        console.log(`Znaleziono: ${positions.length} pozycji\n`);
        positions.forEach((pos, i) => {
            const snr = pos.snr ? `SNR: ${pos.snr.toFixed(1)}dB` : 'SNR: brak';
            const rssi = pos.rssi ? `RSSI: ${pos.rssi}dBm` : 'RSSI: brak';
            const alt = pos.altitude ? `${pos.altitude}m` : 'brak';
            console.log(`${i + 1}. ${pos.nodeId} (${pos.node.longName || 'Unknown'})`);
            console.log(`   ${pos.latitude.toFixed(5)}, ${pos.longitude.toFixed(5)} | Alt: ${alt}`);
            console.log(`   ${snr} | ${rssi} | ${new Date(pos.timestamp).toLocaleString()}`);
            console.log();
        });

        // 2. Ostatnia telemetria
        console.log('\n📊 === OSTATNIA 20 TELEMETRII ===');
        const telemetry = await prisma.telemetry.findMany({
            take: 20,
            orderBy: { timestamp: 'desc' },
            include: { node: true },
        });

        console.log(`Znaleziono: ${telemetry.length} rekordów telemetrii\n`);
        telemetry.forEach((tel, i) => {
            console.log(`${i + 1}. ${tel.nodeId} (${tel.node.longName || 'Unknown'})`);
            console.log(`   Typ: ${tel.variant || 'unknown'}`);
            if (tel.batteryLevel) console.log(`   Bateria: ${tel.batteryLevel}%`);
            if (tel.voltage) console.log(`   Napięcie: ${tel.voltage.toFixed(2)}V`);
            if (tel.temperature) console.log(`   Temperatura: ${tel.temperature.toFixed(1)}°C`);
            if (tel.relativeHumidity) console.log(`   Wilgotność: ${tel.relativeHumidity.toFixed(0)}%`);
            if (tel.uptimeSeconds) console.log(`   Uptime: ${Math.floor(tel.uptimeSeconds / 3600)}h ${Math.floor((tel.uptimeSeconds % 3600) / 60)}m`);
            if (tel.numPacketsTx) console.log(`   Pakiety TX: ${tel.numPacketsTx}, RX: ${tel.numPacketsRx}`);
            console.log(`   Data: ${new Date(tel.timestamp).toLocaleString()}`);
            console.log();
        });

        // 3. Ostatnie traceroutes
        console.log('\n🛤️  === OSTATNIE 10 TRACEROUTES ===');
        const traceroutes = await prisma.traceroute.findMany({
            take: 10,
            orderBy: { timestamp: 'desc' },
            include: {
                hops: {
                    orderBy: { hopNumber: 'asc' },
                },
            },
        });

        console.log(`Znaleziono: ${traceroutes.length} traceroutes\n`);
        traceroutes.forEach((tr, i) => {
            console.log(`${i + 1}. ${tr.sourceNode} → ${tr.destNode}`);
            console.log(`   Hopy (${tr.hops.length}): ${tr.hops.map(h => {
                const snr = h.snr ? ` (${h.snr.toFixed(1)}dB)` : '';
                return h.nodeId.slice(0, 8) + snr;
            }).join(' → ')}`);
            console.log(`   Data: ${new Date(tr.timestamp).toLocaleString()}`);
            console.log();
        });

        // 4. Ostatnie węzły
        console.log('\n👥 === OSTATNIE 20 AKTYWNYCH WĘZŁÓW ===');
        const nodes = await prisma.node.findMany({
            take: 20,
            orderBy: { lastSeen: 'desc' },
            include: {
                _count: {
                    select: {
                        positions: true,
                        telemetry: true,
                    },
                },
            },
        });

        console.log(`Znaleziono: ${nodes.length} węzłów\n`);
        nodes.forEach((node, i) => {
            console.log(`${i + 1}. ${node.nodeId}`);
            console.log(`   Nazwa: ${node.longName || 'brak'} (${node.shortName || 'brak'})`);
            console.log(`   Pozycje: ${node._count.positions} | Telemetria: ${node._count.telemetry}`);
            console.log(`   Ostatnio: ${new Date(node.lastSeen).toLocaleString()}`);
            console.log();
        });

        // 5. Statystyki ogólne
        console.log('\n📈 === STATYSTYKI OGÓLNE ===');
        const stats = await Promise.all([
            prisma.position.count(),
            prisma.telemetry.count(),
            prisma.traceroute.count(),
            prisma.node.count(),
            prisma.message.count(),
        ]);

        console.log(`Pozycje: ${stats[0]}`);
        console.log(`Telemetria: ${stats[1]}`);
        console.log(`Traceroutes: ${stats[2]}`);
        console.log(`Węzły: ${stats[3]}`);
        console.log(`Wiadomości: ${stats[4]}`);

        // 6. Statystyki SNR/RSSI
        console.log('\n📡 === STATYSTYKI SNR/RSSI ===');
        const positionsWithSignal = await prisma.position.findMany({
            where: {
                OR: [
                    { snr: { not: null } },
                    { rssi: { not: null } },
                ],
            },
            take: 100,
        });

        const withSnr = positionsWithSignal.filter(p => p.snr !== null).length;
        const withRssi = positionsWithSignal.filter(p => p.rssi !== null).length;

        console.log(`Pozycje z SNR: ${withSnr}/${stats[0]} (${((withSnr / stats[0]) * 100).toFixed(1)}%)`);
        console.log(`Pozycje z RSSI: ${withRssi}/${stats[0]} (${((withRssi / stats[0]) * 100).toFixed(1)}%)`);

        // 7. Statystyki telemetrii według typu
        console.log('\n📊 === STATYSTYKI TELEMETRII WEDŁUG TYPU ===');
        const telemetryByVariant = await prisma.telemetry.groupBy({
            by: ['variant'],
            _count: true,
        });

        telemetryByVariant.forEach(v => {
            console.log(`${v.variant || 'unknown'}: ${v._count} rekordów`);
        });

    } catch (error) {
        console.error('❌ Błąd:', error);
    } finally {
        await prisma.$disconnect();
    }
}

checkDatabase();
