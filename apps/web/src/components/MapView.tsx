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
            style: 'mapbox://styles/mapbox/navigation-night-v1', // Premium dark tactical style
            center: [0, 20],
            zoom: 2,
            projection: { name: 'globe' } // 3D Globe view
        });

        map.current.on('load', () => {
            setMapLoaded(true);
        });

        return () => {
            map.current?.remove();
        };
    }, []);

    // Update hexagons on map
    useEffect(() => {
        if (!map.current || !mapLoaded || !hexagons) return;

        const sourceId = 'hexagons';

        // Remove existing source and layer if present
        if (map.current.getLayer(sourceId)) {
            map.current.removeLayer(sourceId);
        }
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
        map.current.on('click', sourceId, (e) => {
            if (!e.features || e.features.length === 0) return;

            const feature = e.features[0];
            const props = feature.properties;

            new mapboxgl.Popup({ closeButton: false, className: 'bg-black/80 text-white' })
                .setLngLat(e.lngLat)
                .setHTML(
                    `<div class="p-2 text-gray-900">
            <h3 class="font-bold">Hexagon ${props?.hexId}</h3>
            <p>Messages: ${props?.messageCount}</p>
            <p>Last seen: ${new Date(props?.lastSeen).toLocaleString()}</p>
          </div>`
                )
                .addTo(map.current!);
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
            <div className="absolute top-4 left-4 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg p-4 z-10">
                <h2 className="text-xl font-bold mb-2">MeshScout</h2>
                <div className="space-y-1 text-sm">
                    <p>Active Hexagons: <span className="font-semibold">{hexagons?.length || 0}</span></p>
                    <p>Total Messages: <span className="font-semibold">
                        {hexagons?.reduce((sum, h) => sum + h.messageCount, 0) || 0}
                    </span></p>
                </div>
            </div>

            {/* Legend */}
            <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg p-4 z-10">
                <h3 className="font-bold mb-2 text-sm">Message Count</h3>
                <div className="space-y-1 text-xs">
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded" style={{ backgroundColor: '#3b82f6' }}></div>
                        <span>0-10</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded" style={{ backgroundColor: '#8b5cf6' }}></div>
                        <span>10-50</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded" style={{ backgroundColor: '#ec4899' }}></div>
                        <span>50-100</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded" style={{ backgroundColor: '#ef4444' }}></div>
                        <span>100+</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
