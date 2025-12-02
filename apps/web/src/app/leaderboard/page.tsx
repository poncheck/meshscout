'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';

const fetcher = (url: string) => fetch(url).then((res) => res.json());

interface Player {
    id: string;
    nodeId: string;
    longName?: string;
    shortName?: string;
    points: number;
    registeredAt: string;
}

export default function LeaderboardPage() {
    const [apiUrl, setApiUrl] = useState('');

    useEffect(() => {
        const hostname = window.location.hostname;
        const port = '3001';
        setApiUrl(`http://${hostname}:${port}`);
    }, []);

    const { data: players, isLoading } = useSWR<Player[]>(
        apiUrl ? `${apiUrl}/api/leaderboard` : null,
        fetcher,
        { refreshInterval: 30000 }
    );

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-8">
            <div className="max-w-4xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-4xl font-bold text-white mb-2">🏆 Leaderboard</h1>
                    <p className="text-purple-200">Top players by traceroute distance</p>
                </div>

                {isLoading ? (
                    <div className="text-white text-center py-12">Loading...</div>
                ) : (
                    <div className="bg-white/10 backdrop-blur-md rounded-xl shadow-2xl overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead className="bg-purple-600/50">
                                    <tr>
                                        <th className="px-6 py-4 text-left text-sm font-semibold text-white">Rank</th>
                                        <th className="px-6 py-4 text-left text-sm font-semibold text-white">Node ID</th>
                                        <th className="px-6 py-4 text-left text-sm font-semibold text-white">Name</th>
                                        <th className="px-6 py-4 text-right text-sm font-semibold text-white">Points</th>
                                        <th className="px-6 py-4 text-right text-sm font-semibold text-white">Registered</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/10">
                                    {players?.map((player, index) => (
                                        <tr
                                            key={player.id}
                                            className="hover:bg-white/5 transition-colors"
                                        >
                                            <td className="px-6 py-4 text-white font-bold">
                                                {index === 0 && '🥇'}
                                                {index === 1 && '🥈'}
                                                {index === 2 && '🥉'}
                                                {index > 2 && `#${index + 1}`}
                                            </td>
                                            <td className="px-6 py-4 text-purple-200 font-mono text-sm">
                                                {player.nodeId}
                                            </td>
                                            <td className="px-6 py-4 text-white">
                                                {player.longName || player.shortName || 'Anonymous'}
                                            </td>
                                            <td className="px-6 py-4 text-right text-white font-semibold">
                                                {player.points.toLocaleString()}
                                            </td>
                                            <td className="px-6 py-4 text-right text-purple-200 text-sm">
                                                {new Date(player.registeredAt).toLocaleDateString()}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                <div className="mt-8 text-center">
                    <a
                        href="/"
                        className="inline-block px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-lg transition-colors"
                    >
                        ← Back to Map
                    </a>
                </div>

                <div className="mt-12 bg-white/5 backdrop-blur-sm rounded-lg p-6 text-purple-100">
                    <h2 className="text-xl font-bold mb-3">How to Play</h2>
                    <ol className="space-y-2 text-sm">
                        <li>1. Send <code className="bg-black/30 px-2 py-1 rounded">!registerme</code> on a public Meshtastic channel</li>
                        <li>2. Your traceroutes will be tracked automatically</li>
                        <li>3. Earn 1 point per kilometer of verified traceroute distance</li>
                        <li>4. Climb the leaderboard! 🚀</li>
                    </ol>
                </div>
            </div>
        </div>
    );
}
