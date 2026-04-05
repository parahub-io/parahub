#!/usr/bin/env bash
# backup_db.sh — Automated PostgreSQL backup for parahub
# Daily pg_dump (custom format) with rotation: 7 daily + 4 weekly
# Run by systemd timer parahub-backup.timer at 04:00 UTC
#
# Restore:
#   sudo -u postgres psql -d parahub -c "SELECT timescaledb_pre_restore();"
#   sudo -u postgres pg_restore -d parahub --no-owner --no-acl <dump_file>
#   sudo -u postgres psql -d parahub -c "SELECT timescaledb_post_restore();"

set -euo pipefail

BACKUP_DIR="/opt/parahub/backups"
DB_NAME="parahub"
DAILY_KEEP=7
WEEKLY_KEEP=4

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DAY_OF_WEEK=$(date +%u)  # 1=Mon, 7=Sun

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

DUMP_FILE="$BACKUP_DIR/daily/${DB_NAME}_${TIMESTAMP}.dump"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Starting backup of $DB_NAME..."

# pg_dump: custom format (-Fc) = compressed + selective restore
sudo -u postgres pg_dump -Fc --no-owner --no-acl "$DB_NAME" > "$DUMP_FILE"

# Verify dump is not trivially small (expect >100MB for 30GB DB)
DUMP_SIZE=$(stat -c %s "$DUMP_FILE")
if [ "$DUMP_SIZE" -lt 1048576 ]; then
    echo "ERROR: Dump file too small ($(numfmt --to=iec-i "$DUMP_SIZE")), likely failed"
    rm -f "$DUMP_FILE"
    exit 1
fi

echo "Backup created: $DUMP_FILE ($(numfmt --to=iec-i "$DUMP_SIZE"))"

# Weekly copy on Sunday
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    cp "$DUMP_FILE" "$BACKUP_DIR/weekly/"
    echo "Weekly copy created"
fi

# Rotate daily: keep last N
find "$BACKUP_DIR/daily" -name '*.dump' -printf '%T@ %p\n' | sort -rn | tail -n +$((DAILY_KEEP + 1)) | cut -d' ' -f2- | xargs -r rm -f
DAILY_COUNT=$(find "$BACKUP_DIR/daily" -name '*.dump' | wc -l)
echo "Daily backups: $DAILY_COUNT (keeping $DAILY_KEEP)"

# Rotate weekly: keep last N
find "$BACKUP_DIR/weekly" -name '*.dump' -printf '%T@ %p\n' | sort -rn | tail -n +$((WEEKLY_KEEP + 1)) | cut -d' ' -f2- | xargs -r rm -f
WEEKLY_COUNT=$(find "$BACKUP_DIR/weekly" -name '*.dump' | wc -l)
echo "Weekly backups: $WEEKLY_COUNT (keeping $WEEKLY_KEEP)"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Backup completed successfully"
