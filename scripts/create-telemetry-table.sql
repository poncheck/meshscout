-- Create Telemetry table
CREATE TABLE IF NOT EXISTS "Telemetry" (
    id TEXT PRIMARY KEY,
    "nodeId" TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Device metrics
    "batteryLevel" INTEGER,
    voltage DOUBLE PRECISION,
    "channelUtilization" DOUBLE PRECISION,
    "airUtilTx" DOUBLE PRECISION,
    "uptimeSeconds" INTEGER,

    -- Environment metrics
    temperature DOUBLE PRECISION,
    "relativeHumidity" DOUBLE PRECISION,
    "barometricPressure" DOUBLE PRECISION,
    "gasResistance" DOUBLE PRECISION,
    iaq INTEGER,
    distance DOUBLE PRECISION,
    lux DOUBLE PRECISION,
    "whiteLux" DOUBLE PRECISION,
    ir DOUBLE PRECISION,
    uv DOUBLE PRECISION,
    "windDirection" INTEGER,
    "windSpeed" DOUBLE PRECISION,
    "windGust" DOUBLE PRECISION,
    "windLull" DOUBLE PRECISION,

    -- Power metrics
    "ch1Voltage" DOUBLE PRECISION,
    "ch1Current" DOUBLE PRECISION,
    "ch2Voltage" DOUBLE PRECISION,
    "ch2Current" DOUBLE PRECISION,
    "ch3Voltage" DOUBLE PRECISION,
    "ch3Current" DOUBLE PRECISION,

    -- Air quality metrics
    pm10 INTEGER,
    pm25 INTEGER,
    pm100 INTEGER,

    -- Local stats
    "numPacketsTx" INTEGER,
    "numPacketsRx" INTEGER,
    "numPacketsRxBad" INTEGER,
    "numOnlineNodes" INTEGER,
    "numTotalNodes" INTEGER,

    -- Health metrics
    "heartBpm" INTEGER,
    "spO2" INTEGER,
    "bodyTempC" DOUBLE PRECISION,

    -- Metadata
    variant TEXT,

    -- Foreign key
    CONSTRAINT "Telemetry_nodeId_fkey" FOREIGN KEY ("nodeId") REFERENCES "Node"("nodeId") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS "Telemetry_nodeId_idx" ON "Telemetry"("nodeId");
CREATE INDEX IF NOT EXISTS "Telemetry_timestamp_idx" ON "Telemetry"("timestamp");
CREATE INDEX IF NOT EXISTS "Telemetry_variant_idx" ON "Telemetry"("variant");

-- Show success message
SELECT 'Tabela Telemetry została utworzona!' as status;
