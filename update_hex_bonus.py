#!/usr/bin/env python3
"""
Script to update historical hex bonus points from 5 to 50
"""

import sqlite3
import sys

def update_hex_bonuses(db_path='data/mesh_scout.db'):
    """Update all old hex bonuses from 5 to 50 points"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check current state
        cursor.execute("""
            SELECT COUNT(*), MIN(points_earned), MAX(points_earned)
            FROM device_hexagons
        """)
        total, min_points, max_points = cursor.fetchone()
        print(f"📊 Total hexagon records: {total}")
        print(f"📊 Point range: {min_points} to {max_points}")

        # Find records that likely have old bonus (points_earned between 5 and 49)
        cursor.execute("""
            SELECT node_id, h3_index, points_earned, visit_count, traceroutes_here
            FROM device_hexagons
            WHERE points_earned >= 5 AND points_earned < 50
        """)
        old_records = cursor.fetchall()

        if not old_records:
            print("✅ No old hex bonus records found!")
            conn.close()
            return

        print(f"\n🔍 Found {len(old_records)} hexagons with old bonus:")
        for node_id, h3_index, points, visits, traceroutes in old_records[:5]:
            print(f"  - {node_id[:12]}... hex={h3_index[:12]}... points={points} visits={visits} trs={traceroutes}")
        if len(old_records) > 5:
            print(f"  ... and {len(old_records) - 5} more")

        # Update hex bonuses: add 45 points to each (50 - 5 = 45)
        # This assumes all these records got a 5 point bonus initially
        print(f"\n🔧 Updating {len(old_records)} records (adding +45 points)...")

        cursor.execute("""
            UPDATE device_hexagons
            SET points_earned = points_earned + 45
            WHERE points_earned >= 5 AND points_earned < 50
        """)
        updated = cursor.rowcount

        # Also update player_scores totals
        print(f"🔧 Updating player_scores totals...")

        # Add 45 points per affected hex to each player's total
        cursor.execute("""
            UPDATE player_scores
            SET total_points = total_points + (
                SELECT COUNT(*) * 45
                FROM device_hexagons
                WHERE device_hexagons.node_id = player_scores.node_id
                AND points_earned >= 50 AND points_earned < 95
            ),
            hex_bonus_points = hex_bonus_points + (
                SELECT COUNT(*) * 45
                FROM device_hexagons
                WHERE device_hexagons.node_id = player_scores.node_id
                AND points_earned >= 50 AND points_earned < 95
            )
            WHERE node_id IN (
                SELECT DISTINCT node_id
                FROM device_hexagons
                WHERE points_earned >= 50 AND points_earned < 95
            )
        """)

        conn.commit()

        print(f"✅ Updated {updated} hexagon records")
        print(f"✅ Updated player_scores totals")

        # Show summary after update
        cursor.execute("""
            SELECT COUNT(*), MIN(points_earned), MAX(points_earned)
            FROM device_hexagons
        """)
        total, min_points, max_points = cursor.fetchone()
        print(f"\n📊 After update:")
        print(f"   Total hexagon records: {total}")
        print(f"   Point range: {min_points} to {max_points}")

        conn.close()
        print("\n✅ Database update completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    update_hex_bonuses()
