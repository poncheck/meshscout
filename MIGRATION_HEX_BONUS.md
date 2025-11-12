# Hex Bonus Migration Guide

## Overview
This migration updates historical hexagon bonus points from 5 to 50 points.

## What Changed
- Hex bonus increased from **5 points** to **50 points** per new hexagon
- The display now correctly shows:
  - **+50 pkt (bonus)** for hex discovery
  - **Dodatkowe punkty** for distance-based traceroute points from that hex

## How to Run Migration

### Option 1: Manual Execution (Recommended)

If you're running in Docker:

```bash
# Enter your Docker container
docker exec -it <container_name> bash

# Run the migration script
python3 migrate_hex_bonus.py

# Exit container
exit
```

If running locally:

```bash
python3 migrate_hex_bonus.py
```

### Option 2: Automatic on Startup

The migration script is safe to run multiple times (it only updates records with old 5-point bonuses).

You could add it to your startup script or Dockerfile CMD to run automatically.

## What the Migration Does

1. **Finds old records**: Identifies hexagons with 5-point bonuses:
   - `visit_count = 1` (first visit)
   - `traceroutes_here = 0` (no traceroutes yet)
   - `points_earned = 5` (old bonus)

2. **Updates device_hexagons table**:
   - Changes `points_earned` from 5 to 50

3. **Updates player_scores table**:
   - Adds +45 points to `total_points` per affected hex
   - Adds +45 points to `hex_bonus_points` per affected hex

## Verification

After running the migration, check:

```python
# Connect to your database
import sqlite3
conn = sqlite3.connect('meshtastic_messages.db')
cursor = conn.cursor()

# Check if any 5-point bonuses remain
cursor.execute("""
    SELECT COUNT(*) FROM device_hexagons
    WHERE visit_count = 1 AND traceroutes_here = 0 AND points_earned = 5
""")
count = cursor.fetchone()[0]
print(f"Old 5-point bonuses remaining: {count}")  # Should be 0

conn.close()
```

## Notes

- The migration only affects hexagons with **exactly 5 points** and no traceroutes
- Hexagons with traceroute points added will not be affected incorrectly
- Safe to run multiple times - will only update records that need updating
- Player scores are automatically recalculated to reflect the new bonuses

## Questions?

If you encounter any issues, check:
1. Database file path is correct
2. Tables `device_hexagons` and `player_scores` exist
3. You have write permissions to the database
