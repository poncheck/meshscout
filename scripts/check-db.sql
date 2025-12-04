-- Sprawdzenie bazy danych MeshScout

\echo '📊 === STATYSTYKI OGÓLNE ==='
\echo ''

SELECT 'Węzły (Nodes):' as "Tabela", COUNT(*) as "Liczba" FROM "Node"
UNION ALL
SELECT 'Pozycje (Positions):', COUNT(*) FROM "Position"
UNION ALL
SELECT 'Telemetria (Telemetry):', COUNT(*) FROM "Telemetry"
UNION ALL
SELECT 'Traceroutes:', COUNT(*) FROM "Traceroute"
UNION ALL
SELECT 'Wiadomości (Messages):', COUNT(*) FROM "Message";

\echo ''
\echo '📍 === OSTATNIE 10 POZYCJI Z SNR/RSSI ==='
\echo ''

SELECT
    "nodeId",
    ROUND(CAST(latitude AS numeric), 5) as lat,
    ROUND(CAST(longitude AS numeric), 5) as lng,
    altitude,
    ROUND(CAST(snr AS numeric), 1) as snr,
    rssi,
    to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') as czas
FROM "Position"
WHERE snr IS NOT NULL OR rssi IS NOT NULL
ORDER BY timestamp DESC
LIMIT 10;

\echo ''
\echo '📊 === OSTATNIA 10 TELEMETRII ==='
\echo ''

SELECT
    "nodeId",
    variant as typ,
    "batteryLevel" as bateria,
    ROUND(CAST(voltage AS numeric), 2) as napięcie,
    ROUND(CAST(temperature AS numeric), 1) as temp,
    ROUND(CAST("relativeHumidity" AS numeric), 0) as wilgotność,
    to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') as czas
FROM "Telemetry"
ORDER BY timestamp DESC
LIMIT 10;

\echo ''
\echo '🛤️  === OSTATNIE 5 TRACEROUTES ==='
\echo ''

SELECT
    "sourceNode" as źródło,
    "destNode" as cel,
    (SELECT COUNT(*) FROM "TracerouteHop" WHERE "tracerouteId" = t.id) as "liczba_hopów",
    to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') as czas
FROM "Traceroute" t
ORDER BY timestamp DESC
LIMIT 5;

\echo ''
\echo '📡 === STATYSTYKI SNR/RSSI ==='
\echo ''

SELECT
    COUNT(*) as "Wszystkie pozycje",
    COUNT(snr) as "Z SNR",
    COUNT(rssi) as "Z RSSI",
    ROUND(CAST(COUNT(snr) AS numeric) * 100.0 / COUNT(*), 1) as "% z SNR",
    ROUND(CAST(COUNT(rssi) AS numeric) * 100.0 / COUNT(*), 1) as "% z RSSI"
FROM "Position";

\echo ''
\echo '📊 === TELEMETRIA WEDŁUG TYPU ==='
\echo ''

SELECT
    COALESCE(variant, 'unknown') as typ,
    COUNT(*) as liczba
FROM "Telemetry"
GROUP BY variant
ORDER BY COUNT(*) DESC;

\echo ''
\echo '👥 === TOP 10 AKTYWNYCH WĘZŁÓW ==='
\echo ''

SELECT
    n."nodeId",
    n."longName",
    n."shortName",
    COUNT(p.id) as pozycje,
    COUNT(t.id) as telemetria,
    to_char(n."lastSeen", 'YYYY-MM-DD HH24:MI:SS') as "ostatnio widziany"
FROM "Node" n
LEFT JOIN "Position" p ON p."nodeId" = n."nodeId"
LEFT JOIN "Telemetry" t ON t."nodeId" = n."nodeId"
GROUP BY n."nodeId", n."longName", n."shortName", n."lastSeen"
ORDER BY n."lastSeen" DESC
LIMIT 10;
