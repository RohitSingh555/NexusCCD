#!/bin/bash

# Daily Client Report Script
# This script sends daily client reports at 11 PM

# Set the project directory
PROJECT_DIR="/home/agilemorph/Desktop/fredvictor/NexusCCD"

# Change to project directory
cd "$PROJECT_DIR"

# Activate virtual environment
source venv/bin/activate

# Send daily client report
python manage.py send_daily_client_report --frequency daily

# Log the execution
echo "$(date): Daily client report sent" >> logs/daily_report.log
