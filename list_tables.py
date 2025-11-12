#!/usr/bin/env python3
"""List all tables in the database"""
import sqlite3

conn = sqlite3.connect('meshtastic_messages.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")
    cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
    count = cursor.fetchone()[0]
    print(f"    (rows: {count})")

conn.close()
