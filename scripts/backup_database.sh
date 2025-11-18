#!/bin/bash

# Database Backup Script
# This script creates a daily backup of the PostgreSQL database
# It replaces the previous backup (only keeps the latest backup)
# Recommended to run daily via cron

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Database configuration (from docker-compose.yml)
DB_NAME="nexusccd_db"
DB_USER="nexusccd_user"
DB_PASSWORD="nexusccd_password"
DB_CONTAINER="nexusccd_db_1"

# Backup directory
BACKUP_DIR="$PROJECT_DIR/backups"
mkdir -p "$BACKUP_DIR"

# Backup filename (single file that gets replaced)
BACKUP_FILE="$BACKUP_DIR/database_backup.sql"

# Log file
LOG_FILE="$PROJECT_DIR/logs/database_backup.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOG_FILE"
}

log_message "Starting database backup..."

# Create backup using pg_dump
# Use production docker-compose if available, otherwise fall back to default
if docker-compose -f docker-compose.prod.yml ps db > /dev/null 2>&1; then
    COMPOSE_FILE="-f docker-compose.prod.yml"
else
    COMPOSE_FILE=""
fi

if docker-compose $COMPOSE_FILE exec -T db pg_dump -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE" 2>>"$LOG_FILE"; then
    # Compress the backup
    if gzip -f "$BACKUP_FILE" 2>>"$LOG_FILE"; then
        BACKUP_FILE="${BACKUP_FILE}.gz"
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        log_message "Database backup completed successfully. Size: $BACKUP_SIZE"
        
        # Keep only the latest backup (remove older backups if any)
        find "$BACKUP_DIR" -name "database_backup.sql.gz" -type f -mtime +1 -delete 2>>"$LOG_FILE"
        
        echo "✅ Backup completed: $BACKUP_FILE ($BACKUP_SIZE)"
        exit 0
    else
        log_message "ERROR: Failed to compress backup file"
        echo "❌ Error: Failed to compress backup"
        exit 1
    fi
else
    log_message "ERROR: Failed to create database backup"
    echo "❌ Error: Failed to create database backup"
    exit 1
fi

