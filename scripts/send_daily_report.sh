#!/bin/bash

# Daily Client Report Script
# This script sends daily client reports
# Recommended to run daily via cron (e.g., at 11 PM)

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Check if docker-compose is available and containers are running
if command -v docker-compose >/dev/null 2>&1 && docker-compose ps | grep -q "Up"; then
    # Use Docker (preferred method)
    docker-compose exec -T web python manage.py send_daily_client_report --frequency daily
elif [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    # Running inside Docker container - use direct command
    python manage.py send_daily_client_report --frequency daily
else
    # Running locally without Docker - use virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    # Send daily client report
    python manage.py send_daily_client_report --frequency daily
fi

# Log the execution
LOG_FILE="$PROJECT_DIR/logs/daily_report.log"
mkdir -p "$(dirname "$LOG_FILE")"
echo "$(date '+%Y-%m-%d %H:%M:%S'): Daily client report sent" >> "$LOG_FILE"
