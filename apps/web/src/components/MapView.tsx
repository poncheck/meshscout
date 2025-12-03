'use client';

import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import useSWR from 'swr';

const fetcher = (url: string) => fetch(url).then((res) => res.json());

interface Hexagon {
    hexId: string;
    messageCount: number;
    lastSeen: string;
    boundary: [number, number][];
}

export default function MapView() {
    const mapContainer = useRef<HTMLDivElement>(null);
    const map = useRef<mapboxgl.Map | null>(null);
    const [mapLoaded, setMapLoaded] = useState(false);

    // Dynamically determine API URL based on current hostname to support network access
    const [apiUrl, setApiUrl] = useState('');

    useEffect(() => {
        const hostname = window.location.hostname;
        const port = '3001';
        setApiUrl(`http://${hostname}:${port}`);
    }, []);

    const { data: hexagons } = useSWR<Hexagon[]>(apiUrl ? `${apiUrl}/api/hexagons` : null, fetcher, {
        refreshInterval: 10000, // Refresh every 10 seconds
    });

    // Initialize map
    useEffect(() => {
        if (map.current || !mapContainer.current) return;

        const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || 'pk.eyJ1IjoicG9uY2hlY2siLCJhIjoiY21pb3hibmsyMDVyejNmc2N2dTA0NnAzOSJ9.VxWyty0zK_90R_Zi3N2QHA';
        if (!token) {
            console.error('Mapbox token is missing!');
        }
        mapboxgl.accessToken = token;

        map.current = new mapboxgl.Map({
            container: mapContainer.current,
            style: 'mapbox://styles/mapbox/dark-v11', // Clean dark style without traffic
            center: [0, 20],
            zoom: 2,
            projection: { name: 'globe' } // 3D Globe view
        });

        map.current.on('load', () => {
            setMapLoaded(true);
        });

        map.current.on('style.load', () => { // Added style.load event for fog
            map.current?.setFog({
                'color': 'rgb(10, 10, 20)', // Lower atmosphere
                'high-color': 'rgb(20, 20, 40)', // Upper atmosphere
                'horizon-blend': 0.2, // Atmosphere thickness (default 0.2 at low zooms)
                'space-color': 'rgb(5, 5, 10)', // Background color
                'star-intensity': 0.6 // Background star brightness (default 0.35 at low zoooms )
            });
        });

        return () => {
            map.current?.remove();
        };
    }, []);

    // Update hexagons on map
    useEffect(() => {
        if (!map.current || !mapLoaded || !hexagons) return;

        console.log('🗺️ Updating map with hexagons:', hexagons.length);
        console.log('🗺️ First hexagon sample:', hexagons[0]);

        const sourceId = 'hexagons';

        // Remove existing layers first (both fill and outline)
        if (map.current.getLayer(sourceId)) {
            map.current.removeLayer(sourceId);
        }
        if (map.current.getLayer(`${sourceId}-outline`)) {
            map.current.removeLayer(`${sourceId}-outline`);
        }

        // Then remove source
        if (map.current.getSource(sourceId)) {
            map.current.removeSource(sourceId);
        }

        // Create GeoJSON from hexagons
        const geojson: GeoJSON.FeatureCollection = {
            type: 'FeatureCollection',
            features: hexagons.map((hex) => ({
                type: 'Feature',
                geometry: {
                    type: 'Polygon',
                    coordinates: [
                        hex.boundary.map(([lat, lng]) => [lng, lat]), // Convert lat/lng to lng/lat
                    ],
                },
                properties: {
                    hexId: hex.hexId,
                    messageCount: hex.messageCount,
                    lastSeen: hex.lastSeen,
                },
            })),
        };

        console.log('🗺️ GeoJSON features:', geojson.features.length);
        console.log('🗺️ First feature:', geojson.features[0]);

        // Add source
        map.current.addSource(sourceId, {
            type: 'geojson',
            data: geojson,
        });

        // Add fill layer
        map.current.addLayer({
            id: sourceId,
            type: 'fill',
            source: sourceId,
            paint: {
                'fill-color': [
                    'interpolate',
                    ['linear'],
                    ['get', 'messageCount'],
                    0, '#3b82f6',
                    10, '#8b5cf6',
                    50, '#ec4899',
                    100, '#ef4444',
                ],
                'fill-opacity': 0.6,
            },
        });

        // Add outline layer
        map.current.addLayer({
            id: `${sourceId}-outline`,
            type: 'line',
            source: sourceId,
            paint: {
                'line-color': '#ffffff',
                'line-width': 1,
                'line-opacity': 0.8,
            },
        });

        // Add click handler
        map.current.on('click', sourceId, async (e) => {
            if (!e.features || e.features.length === 0) return;

            const feature = e.features[0];
            const props = feature.properties;
            const hexId = props?.hexId;

            if (!hexId) return;

            // Remove existing popup if any
            if (activePopup.current) {
                activePopup.current.remove();
                activePopup.current = null;
            }

            // Show loading popup
            const popup = new mapboxgl.Popup({
                closeButton: true,
                className: 'hexagon-popup',
                closeOnClick: true, // Changed to true
                maxWidth: 'none'
            })
                .setLngLat(e.lngLat)
                .setHTML('<div class="p-4"><div class="animate-pulse">Loading...</div></div>')
                .addTo(map.current!);

            activePopup.current = popup; // Assign new popup to ref

            try {
                // Fetch detailed hexagon data
                const apiUrl = typeof window !== 'undefined'
                    ? `http://${window.location.hostname}:3001/api/hexagons/${hexId}`
                    : `/api/hexagons/${hexId}`;

                const response = await fetch(apiUrl);
                const hexagonData = await response.json();

                // Get unique nodes
                const nodes = new Map();
                hexagonData.positions?.forEach((pos: any) => {
                    if (!nodes.has(pos.nodeId)) {
                        nodes.set(pos.nodeId, {
                            nodeId: pos.nodeId,
                            longName: pos.node?.longName || 'Unknown',
                            shortName: pos.node?.shortName || pos.nodeId.slice(0, 8),
                            lastSeen: pos.timestamp,
                            positionCount: 1
                        });
                    } else {
                        nodes.get(pos.nodeId).positionCount++;
                    }
                });

                const nodeList = Array.from(nodes.values());

                // Build popup HTML with dark theme
                const html = `
                    <div class="p-4 min-w-[320px] bg-gray-900 text-white rounded-lg">
                        <h3 class="font-bold text-xl mb-3 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                            📍 Hexagon ${hexId.slice(0, 12)}...
                        </h3>
                        
                        <div class="mb-4 text-sm space-y-2 bg-gray-800/50 p-3 rounded-lg">
                            <div class="flex justify-between">
                                <span class="text-gray-400">Messages:</span>
                                <span class="font-bold text-blue-400">${hexagonData.messageCount}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">Last Activity:</span>
                                <span class="font-semibold text-gray-200">${new Date(hexagonData.lastSeen).toLocaleString()}</span>
                            </div>
                        </div>

                        ${nodeList.length > 0 ? `
                            <div class="border-t border-gray-700 pt-3">
                                <h4 class="font-bold text-sm mb-3 text-white">🔌 Devices (${nodeList.length})</h4>
                                <div class="max-h-48 overflow-y-auto space-y-2 pr-2">
                                    ${nodeList.map(node => `
                                        <div class="text-xs bg-gray-800 p-3 rounded-lg border border-gray-700 hover:border-blue-500 transition-colors">
                                            <div class="font-bold text-white mb-1">${node.longName}</div>
                                            <div class="text-gray-400">ID: <span class="text-blue-400 font-mono">${node.shortName}</span></div>
                                            <div class="text-gray-500 text-[10px] mt-1">📍 ${node.positionCount} position${node.positionCount > 1 ? 's' : ''}</div>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : '<div class="text-gray-500 text-sm text-center py-4">No devices detected</div>'}
                    </div>
                `;

                popup.setHTML(html);
            } catch (error) {
                console.error('Error fetching hexagon details:', error);
                popup.setHTML(`
                    <div class="p-4 bg-gray-900 text-white rounded-lg">
                        <h3 class="font-bold text-red-400 mb-2">⚠️ Error</h3>
                        <p class="text-sm text-gray-400">Failed to load hexagon details</p>
                    </div>
                `);
            }
        });

        // Change cursor on hover
        map.current.on('mouseenter', sourceId, () => {
            if (map.current) map.current.getCanvas().style.cursor = 'pointer';
        });

        map.current.on('mouseleave', sourceId, () => {
            if (map.current) map.current.getCanvas().style.cursor = '';
        });
    }, [hexagons, mapLoaded]);

    return (
        <div className="relative w-full h-[100vh]">
            <div ref={mapContainer} className="absolute inset-0 w-full h-full" />

            {/* Stats overlay */}
            <div className="absolute top-4 left-4 bg-gray-900/95 backdrop-blur-sm rounded-lg shadow-2xl p-4 z-10 border border-gray-700">
                <h2 className="text-2xl font-bold mb-3 text-white bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                    MeshScout
                </h2>
                <div className="space-y-2 text-sm text-gray-200">
                    <p className="flex justify-between gap-4">
                        <span className="text-gray-400">Active Hexagons:</span>
                        <span className="font-bold text-blue-400">{hexagons?.length || 0}</span>
                    </p>
                    <p className="flex justify-between gap-4">
                        <span className="text-gray-400">Total Messages:</span>
                        <span className="font-bold text-purple-400">
                            {hexagons?.reduce((sum, h) => sum + h.messageCount, 0) || 0}
                        </span>
                    </p>
                </div>
            </div>

            {/* Legend */}
            <div className="absolute bottom-4 right-4 bg-gray-900/95 backdrop-blur-sm rounded-lg shadow-2xl p-4 z-10 border border-gray-700">
                <h3 className="font-bold mb-3 text-sm text-white">Message Activity</h3>
                <div className="space-y-2 text-xs">
                    <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded-md shadow-lg" style={{ backgroundColor: '#3b82f6' }}></div>
                        <span className="text-gray-300 font-medium">0-10 messages</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded-md shadow-lg" style={{ backgroundColor: '#8b5cf6' }}></div>
                        <span className="text-gray-300 font-medium">10-50 messages</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded-md shadow-lg" style={{ backgroundColor: '#ec4899' }}></div>
                        <span className="text-gray-300 font-medium">50-100 messages</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded-md shadow-lg" style={{ backgroundColor: '#ef4444' }}></div>
                        <span className="text-gray-300 font-medium">100+ messages</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
