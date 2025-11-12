# Database Recovery and Corruption Fix

## Problem
The Mesh Scout database was experiencing recurring corruption with SQLite btree errors:
```
Tree 2 page 901701: btreeInitPage() returns error code 11
```

Error code 11 is `SQLITE_CORRUPT`, indicating database file corruption.

## Root Cause
The previous repair mechanism attempted to fix corruption using `PRAGMA writable_schema`, which doesn't actually repair btree corruption. This caused the corruption to persist, triggering repeated error messages without actual recovery.

## Solution Implemented

### 1. Robust Database Recovery (`_recover_corrupted_database`)
When corruption is detected, the system now:

1. **Creates timestamped backup** of the corrupted database
   - Format: `mesh_scout.corrupted.YYYYMMDD_HHMMSS.db`
   - Preserves data for forensic analysis

2. **Attempts data recovery** using two methods:
   - **Method 1**: SQLite `.recover` command (requires SQLite 3.37.0+)
     - Extracts maximum recoverable data from corrupted database
   - **Method 2**: SQLite `.dump` command (fallback)
     - Exports SQL schema and partial data

3. **Removes corrupted files**:
   - Deletes `mesh_scout.db`
   - Deletes WAL file (`mesh_scout.db-wal`)
   - Deletes SHM file (`mesh_scout.db-shm`)

4. **Imports recovered data** into fresh database
   - If recovery successful, imports SQL dump
   - If recovery fails, creates empty database

### 2. Preventive Measures

Changed PRAGMA settings to reduce corruption risk:

```python
PRAGMA synchronous=FULL           # Full synchronization (was NORMAL)
PRAGMA wal_autocheckpoint=1000    # Checkpoint every 1000 pages
PRAGMA page_size=4096             # Standard page size
PRAGMA auto_vacuum=INCREMENTAL    # Automatic cleanup
```

**Key change**: `synchronous=FULL` ensures all data is written to disk before transactions complete, preventing corruption from unexpected shutdowns or crashes.

### 3. Graceful Shutdown with WAL Checkpoint

The `close()` method now:
- Executes `PRAGMA wal_checkpoint(TRUNCATE)` before closing
- Ensures WAL file is merged into main database
- Reduces risk of corruption on restart

### 4. Database Health Monitoring

New endpoints and methods:
- `verify_integrity()`: Checks database integrity using `PRAGMA integrity_check`
- `checkpoint_wal()`: Manually triggers WAL checkpoint
- `/api/database/health`: HTTP endpoint for monitoring database health

## Usage

### Monitoring Database Health

```bash
curl http://localhost:5000/api/database/health
```

Response:
```json
{
  "success": true,
  "database_healthy": true,
  "database_size_mb": 123.45,
  "wal_size_mb": 2.1,
  "status": "healthy"
}
```

### Manual Recovery

If you need to manually recover a corrupted database:

```bash
# Method 1: Using .recover (SQLite 3.37.0+)
sqlite3 data/mesh_scout.db ".recover" > recovered.sql
mv data/mesh_scout.db data/mesh_scout.corrupted.backup.db
sqlite3 data/mesh_scout.db < recovered.sql

# Method 2: Using .dump (older SQLite)
sqlite3 data/mesh_scout.db ".dump" > recovered.sql
mv data/mesh_scout.db data/mesh_scout.corrupted.backup.db
sqlite3 data/mesh_scout.db < recovered.sql
```

### Automatic Recovery

The system now automatically recovers when corruption is detected during:
- Application startup
- Database initialization
- Any database operation that triggers `DatabaseError`

## Testing

The fix was tested with:
1. Artificially corrupted database files
2. Integrity check verification
3. Recovery process validation

## Performance Impact

- **Minimal impact**: `synchronous=FULL` adds ~10-20% write overhead
- **Benefit**: Significantly reduced corruption risk
- **Recommended**: For production systems where data integrity is critical

## Monitoring Recommendations

1. **Set up health check monitoring**:
   ```bash
   */5 * * * * curl -s http://localhost:5000/api/database/health | grep -q '"database_healthy":true' || echo "Database corruption detected!"
   ```

2. **Monitor WAL file size**:
   - Large WAL files (>50MB) may indicate checkpoint issues
   - Automatic checkpoint triggers at 10MB via health endpoint

3. **Check backup files**:
   ```bash
   ls -lh data/*.corrupted.*.db
   ```

## Files Modified

1. `database.py`:
   - Added `_recover_corrupted_database()` method
   - Updated `_init_database()` to use new recovery
   - Changed PRAGMA settings for safety
   - Added `verify_integrity()` and `checkpoint_wal()` methods
   - Updated `close()` to perform checkpoint

2. `web_server.py`:
   - Added `/api/database/health` endpoint

## Emergency Recovery

If automatic recovery fails:

1. **Backup current state**:
   ```bash
   cp -r data data.backup.$(date +%Y%m%d_%H%M%S)
   ```

2. **Delete corrupted files**:
   ```bash
   rm data/mesh_scout.db*
   ```

3. **Restart application**:
   - Fresh database will be created automatically
   - Historical data will be lost, but system will function

4. **Restore from timestamped backup** (if needed):
   ```bash
   # Find latest backup
   ls -lt data/*.corrupted.*.db
   # Try to recover
   sqlite3 data/mesh_scout.corrupted.20231113_123456.db ".recover" > recovered.sql
   sqlite3 data/mesh_scout.db < recovered.sql
   ```

## Prevention Best Practices

1. **Use Docker volumes** for database persistence
2. **Implement regular backups** (daily recommended)
3. **Monitor disk space** (corruption can occur when disk is full)
4. **Graceful shutdowns** (avoid SIGKILL, use SIGTERM)
5. **Use health checks** in production
6. **Regular integrity checks** (automated via cron)

## Related Issues

- Original issue: Recurring btree corruption errors
- Previous PR: #9, #8, #7 (partial fixes)
- Solution: Complete database recovery and prevention system
