#!/usr/bin/env python3
"""
Database migration script to update hex bonus from 5 to 50 points.
This should be run once to update historical data.
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_hex_bonus(db_path='meshtastic_messages.db'):
    """
    Migrates old hex bonus records from 5 points to 50 points.

    This updates:
    1. device_hexagons.points_earned - adds 45 points to records with old bonus
    2. player_scores.total_points - adds 45 points per affected hex
    3. player_scores.hex_bonus_points - adds 45 points per affected hex
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='device_hexagons'")
        if not cursor.fetchone():
            logger.info("✅ Table device_hexagons doesn't exist yet - migration not needed")
            conn.close()
            return

        logger.info("🔍 Checking for old hex bonus records...")

        # Find hexagons that might have old bonus
        # Logic: If a hexagon has exactly 50 points or more, it's likely already updated
        # If it has less than 50 points, it might have old 5 point bonus
        # We need to be careful not to update hexagons that have 0 traceroutes and low points legitimately

        # Better approach: Find hexagons where points_earned < 50 AND visit_count = 1 (first visit)
        # These are likely candidates for having the old 5-point bonus
        cursor.execute("""
            SELECT node_id, h3_index, points_earned, visit_count, traceroutes_here, first_visit
            FROM device_hexagons
            WHERE visit_count = 1 AND traceroutes_here = 0 AND points_earned = 5
        """)

        candidates = cursor.fetchall()

        if not candidates:
            logger.info("✅ No old hex bonus records found (all bonuses are already 50 points)")
            conn.close()
            return

        logger.info(f"📊 Found {len(candidates)} hexagons with 5-point bonus:")
        for node_id, h3_index, points, visits, traceroutes, first_visit in candidates[:10]:
            logger.info(f"   {node_id[:16]}... hex={h3_index[:16]}... points={points} first_visit={first_visit}")
        if len(candidates) > 10:
            logger.info(f"   ... and {len(candidates) - 10} more")

        # Update device_hexagons: change 5 points to 50 points
        logger.info(f"🔧 Updating {len(candidates)} hexagon records...")
        cursor.execute("""
            UPDATE device_hexagons
            SET points_earned = 50
            WHERE visit_count = 1 AND traceroutes_here = 0 AND points_earned = 5
        """)
        updated_hexagons = cursor.rowcount

        # Update player_scores: add 45 points per affected hex (50 - 5 = 45)
        logger.info(f"🔧 Updating player_scores totals...")

        # Get list of affected players and how many hexes they have
        cursor.execute("""
            SELECT node_id, COUNT(*) as hex_count
            FROM device_hexagons
            WHERE visit_count = 1 AND traceroutes_here = 0 AND points_earned = 50
            GROUP BY node_id
        """)

        affected_players = cursor.fetchall()

        for node_id, hex_count in affected_players:
            additional_points = hex_count * 45  # 45 = 50 - 5
            cursor.execute("""
                UPDATE player_scores
                SET total_points = total_points + ?,
                    hex_bonus_points = hex_bonus_points + ?
                WHERE node_id = ?
            """, (additional_points, additional_points, node_id))
            logger.info(f"   Updated player {node_id[:16]}... (+{additional_points} points for {hex_count} hexes)")

        conn.commit()

        logger.info(f"✅ Migration completed successfully!")
        logger.info(f"   - Updated {updated_hexagons} hexagon records")
        logger.info(f"   - Updated {len(affected_players)} player score records")

        conn.close()

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    migrate_hex_bonus()
