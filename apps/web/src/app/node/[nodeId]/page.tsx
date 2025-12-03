'use client';

import { useParams } from 'next/navigation';
import useSWR from 'swr';
import Link from 'next/link';
import { useState, useEffect } from 'react';

const fetcher = (url: string) => fetch(url).then((res) => res.json());

interface Position {
    id: string;
    latitude: number;
    longitude: number;
    altitude: number | null;
    timestamp: string;
    snr: number | null;
    rssi: number | null;
}

interface TracerouteHop {
    id: string;
    hopNumber: number;
    nodeId: string;
    snr: number | null;
}

interface Traceroute {
    id: string;
    destNode: string;
    timestamp: string;
    hops: TracerouteHop[];
}

interface NodeDetails {
    nodeId: string;
    longName: string | null;
    shortName: string | null;
    lastSeen: string;
    positions: Position[];
    traceroutes: Traceroute[];
}

export default function NodeDetailsPage() {
    const params = useParams();
    const nodeId = params?.nodeId as string;
    const [apiUrl, setApiUrl] = useState('');

    useEffect(() => {
        const hostname = window.location.hostname;
        const port = '3001';
        setApiUrl(`http://${hostname}:${port}`);
    }, []);

    const { data: node, error } = useSWR<NodeDetails>(
        apiUrl && nodeId ? `${apiUrl}/api/nodes/${nodeId}` : null,
        fetcher,
        { refreshInterval: 10000 }
    );

    if (error) return <div className="p-8 text-red-500">Failed to load node details</div>;
    if (!node) return <div className="p-8 text-white">Loading...</div>;

    return (
        <div className="min-h-screen bg-gray-950 text-white p-6">
            <div className="max-w-6xl mx-auto">
                <div className="mb-6 flex items-center gap-4">
                    <Link href="/" className="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700 transition">
                        ← Back to Map
                    </Link>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                        {node.longName || 'Unknown Node'}
                        <span className="text-gray-500 text-xl ml-3 font-mono">({node.shortName || nodeId})</span>
                    </h1>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    {/* Info Card */}
                    <div className="bg-gray-900 p-6 rounded-xl border border-gray-800">
                        <h2 className="text-xl font-semibold mb-4 text-blue-400">Device Info</h2>
                        <div className="space-y-3">
                            <div className="flex justify-between border-b border-gray-800 pb-2">
                                <span className="text-gray-400">Node ID</span>
                                <span className="font-mono">{node.nodeId}</span>
                            </div>
                            <div className="flex justify-between border-b border-gray-800 pb-2">
                                <span className="text-gray-400">Last Seen</span>
                                <span>{new Date(node.lastSeen).toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between border-b border-gray-800 pb-2">
                                <span className="text-gray-400">Total Positions</span>
                                <span>{node.positions.length}</span>
                            </div>
                        </div>
                    </div>

                    {/* Recent Telemetry (Latest Position) */}
                    <div className="bg-gray-900 p-6 rounded-xl border border-gray-800">
                        <h2 className="text-xl font-semibold mb-4 text-green-400">Latest Telemetry</h2>
                        {node.positions.length > 0 ? (
                            <div className="space-y-3">
                                <div className="flex justify-between border-b border-gray-800 pb-2">
                                    <span className="text-gray-400">Altitude</span>
                                    <span>{node.positions[0].altitude?.toFixed(1) || 'N/A'} m</span>
                                </div>
                                <div className="flex justify-between border-b border-gray-800 pb-2">
                                    <span className="text-gray-400">SNR</span>
                                    <span>{node.positions[0].snr?.toFixed(2) || 'N/A'} dB</span>
                                </div>
                                <div className="flex justify-between border-b border-gray-800 pb-2">
                                    <span className="text-gray-400">RSSI</span>
                                    <span>{node.positions[0].rssi || 'N/A'} dBm</span>
                                </div>
                            </div>
                        ) : (
                            <div className="text-gray-500">No telemetry data available</div>
                        )}
                    </div>
                </div>

                {/* Telemetry History Table */}
                <div className="mb-8">
                    <h2 className="text-2xl font-bold mb-4">Telemetry History</h2>
                    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
                        <table className="w-full text-left">
                            <thead className="bg-gray-800 text-gray-400">
                                <tr>
                                    <th className="p-4">Time</th>
                                    <th className="p-4">Altitude</th>
                                    <th className="p-4">SNR</th>
                                    <th className="p-4">RSSI</th>
                                    <th className="p-4">Coordinates</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-800">
                                {node.positions.map((pos) => (
                                    <tr key={pos.id} className="hover:bg-gray-800/50">
                                        <td className="p-4 text-gray-300">{new Date(pos.timestamp).toLocaleString()}</td>
                                        <td className="p-4 font-mono text-blue-300">{pos.altitude || '-'} m</td>
                                        <td className="p-4 font-mono text-green-300">{pos.snr?.toFixed(2) || '-'} dB</td>
                                        <td className="p-4 font-mono text-yellow-300">{pos.rssi || '-'} dBm</td>
                                        <td className="p-4 font-mono text-gray-400 text-sm">
                                            {pos.latitude.toFixed(5)}, {pos.longitude.toFixed(5)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Traceroutes */}
                <div>
                    <h2 className="text-2xl font-bold mb-4">Traceroutes Initiated</h2>
                    <div className="grid gap-4">
                        {node.traceroutes.length > 0 ? (
                            node.traceroutes.map((tr) => (
                                <div key={tr.id} className="bg-gray-900 p-4 rounded-xl border border-gray-800">
                                    <div className="flex justify-between mb-2">
                                        <span className="font-bold text-purple-400">To: {tr.destNode}</span>
                                        <span className="text-gray-500 text-sm">{new Date(tr.timestamp).toLocaleString()}</span>
                                    </div>
                                    <div className="flex items-center gap-2 overflow-x-auto py-2">
                                        <div className="px-3 py-1 bg-blue-900/50 rounded text-sm border border-blue-800">
                                            Start
                                        </div>
                                        {tr.hops.map((hop) => (
                                            <div key={hop.id} className="flex items-center gap-2">
                                                <span className="text-gray-600">→</span>
                                                <div className="px-3 py-1 bg-gray-800 rounded text-sm border border-gray-700">
                                                    {hop.nodeId.slice(0, 8)}
                                                    {hop.snr && <span className="ml-2 text-xs text-green-500">{hop.snr.toFixed(1)}dB</span>}
                                                </div>
                                            </div>
                                        ))}
                                        <div className="flex items-center gap-2">
                                            <span className="text-gray-600">→</span>
                                            <div className="px-3 py-1 bg-purple-900/50 rounded text-sm border border-purple-800">
                                                End
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="text-gray-500 italic">No traceroutes found</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
