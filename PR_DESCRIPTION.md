# Fix Meshtastic packet decryption and improve UI

## 🔐 Meshtastic Decryption Implementation

### Key Features
- **AES-128/256-CTR decryption** matching meshtastic-map implementation exactly
- **Multi-key support** - configure multiple PSKs via `CHANNEL_KEYS` environment variable
- **Proper nonce construction** - packetId (64-bit LE) + fromNode (32-bit LE) + blockCounter (32-bit LE)
- **Key padding** - short PSKs are zero-padded to 16 bytes for AES-128

### Technical Details
- Supports both 16-byte (AES-128) and 32-byte (AES-256) keys
- Tries all configured keys until one succeeds
- Silent skip for packets with unknown keys (reduces log noise)
- Decrypts ServiceEnvelope → MeshPacket → Data protobuf messages

### Configuration
```bash
# .env
CHANNEL_KEYS="AQ==,<PSK2>,<PSK3>"  # Comma-separated base64 PSKs
```

## 🎨 UI Improvements

### Removed from Node Details Page
- **Position History table** - redundant with map visualization
- **Signal Quality card** - simplified to Device Info + Telemetry only

### Updated Layout
- Changed grid from 3 columns to 2 columns for cleaner look
- Kept essential info: Device Info, Telemetry, Telemetry History, Traceroutes

## 🐛 Bug Fixes

### Database Connection
- Fixed `check-db.sh` to strip query parameters for psql compatibility
- Fixed hostname resolution (postgres → localhost for host access)
- Updated DATABASE_URL with correct Docker credentials in `.env.example`

### Environment Configuration
- Added `CHANNEL_KEYS` support for encryption
- Updated `MQTT_TOPIC` to `msh/#` for all messages
- Fixed `.env` file loading in Docker containers

## 📊 Current Performance

### Data Collection (working as of this PR)
- **Hexagons**: 334
- **Nodes**: 711
- **Positions**: 2,345
- **Messages**: 8,026

### Decode Rate
- **Received**: ~4,000 packets / 5 min
- **Decoded**: ~200 packets / 5 min (~5%)
- **Reason**: 95% of packets use regional PSKs not yet configured

## 🚀 Next Steps

To achieve full coverage (~1,700 hexagons expected):
1. Obtain PSK keys for Polish Meshtastic channels (`/e/ShortFast`, `/e/MediumFast`, `/e/LongFast`)
2. Add them to `CHANNEL_KEYS` in `.env`
3. Restart ingestion service
4. Expected result: 20x increase in decoded packets

## 🔗 References

Implementation based on:
- [meshtastic-map](https://github.com/liamcottle/meshtastic-map) - decryption reference
- [Meshtastic encryption docs](https://meshtastic.org/docs/overview/encryption/)

## 📝 Commits

- feat: Add decryption support for Meshtastic packets using default channel key
- feat: Add detailed logging for encryption/decryption debugging
- feat: Reduce logging noise from failed decryption attempts
- feat: Add support for multiple channel encryption keys from environment
- fix: Match meshtastic-map decryption implementation exactly (AES-128/256, nonce, key padding)
- fix: Update DATABASE_URL with correct Docker credentials in .env.example
- fix: Strip query parameters from DATABASE_URL in check-db.sh for psql compatibility
- fix: Replace postgres hostname with localhost in check-db.sh for host access
- feat: Remove Position History section from node details page
- feat: Remove Signal Quality card from node details page

## ✅ Testing

Tested with:
- Public MQTT broker: `mqtt://mqtt.meshtastic.org`
- Topic: `msh/#` (all regions, all message types)
- Successfully decoding unencrypted packets and default-key packets
- Database correctly storing positions with H3 hexagon indexing
