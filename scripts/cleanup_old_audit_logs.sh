#!/bin/bash

# Cleanup Old Audit Logs Script
# This script deletes audit logs older than 15 days
# Also cleans up delete audit log entries older than 7 days
# Recommended to run daily via cron

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    # Running in Docker - use docker-compose
    # Clean up delete records older than 7 days, and other records older than 15 days
    docker-compose exec -T web python manage.py cleanup_old_audit_logs --cleanup-deletes --delete-days 7 --days 15
else
    # Running locally - use virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    # Run the management command
    # Clean up delete records older than 7 days, and other records older than 15 days
    python manage.py cleanup_old_audit_logs --cleanup-deletes --delete-days 7 --days 15
fi

# Log the execution
LOG_FILE="$PROJECT_DIR/logs/audit_cleanup.log"
mkdir -p "$(dirname "$LOG_FILE")"
echo "$(date '+%Y-%m-%d %H:%M:%S'): Audit log cleanup executed (delete records: 7 days, others: 15 days)" >> "$LOG_FILE"

