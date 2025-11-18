#!/bin/bash

# Script to check if all crons are configured for production database
# This verifies that all cron jobs are pointing to the production database

echo "=========================================="
echo "Cron Configuration Check for Production"
echo "=========================================="
echo ""

PROJECT_DIR="/home/Admin0/NexusCCD"
cd "$PROJECT_DIR"

# Check production database connection
echo "1. Checking Production Database Connection..."
if docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U nexusccd_user -d nexusccd_db > /dev/null 2>&1; then
    PROD_DB_INFO=$(docker-compose -f docker-compose.prod.yml exec -T db psql -U nexusccd_user -d nexusccd_db -t -c "SELECT current_database(), current_user;" 2>/dev/null | tr -d ' ')
    echo "   ✓ Production DB: $PROD_DB_INFO"
else
    echo "   ✗ Production database is not accessible"
    exit 1
fi

echo ""
echo "2. Checking Cron Jobs Configuration..."
echo ""

# Count crons in crontab.txt
CRONS_IN_FILE=$(grep -E "^[0-9]" "$PROJECT_DIR/crontab.txt" | wc -l)
echo "   Crons defined in crontab.txt: $CRONS_IN_FILE"

# Count installed crons
CRONS_INSTALLED=$(crontab -l 2>/dev/null | grep -E "^[0-9]" | wc -l)
echo "   Crons installed in system: $CRONS_INSTALLED"

echo ""
echo "3. Detailed Cron Comparison:"
echo ""

# List crons from crontab.txt
echo "   Expected crons (from crontab.txt):"
grep -E "^[0-9]" "$PROJECT_DIR/crontab.txt" | while read -r line; do
    echo "     - $line"
done

echo ""
echo "   Installed crons (from system):"
crontab -l 2>/dev/null | grep -E "^[0-9]" | while read -r line; do
    echo "     - $line"
done

echo ""
echo "4. Checking if crons use production docker-compose..."
echo ""

# Check if crons use docker-compose.prod.yml
USING_PROD_COMPOSE=$(crontab -l 2>/dev/null | grep -c "docker-compose.prod.yml" || echo "0")
USING_DEFAULT_COMPOSE=$(crontab -l 2>/dev/null | grep -c "docker-compose exec" || echo "0")

if [ "$USING_PROD_COMPOSE" -gt 0 ]; then
    echo "   ✓ Some crons explicitly use docker-compose.prod.yml"
else
    echo "   ⚠ WARNING: No crons explicitly use docker-compose.prod.yml"
    echo "      They may connect to the wrong database if dev containers are running"
fi

echo ""
echo "5. Verifying which database containers are running..."
echo ""

# Check running containers
RUNNING_CONTAINERS=$(docker ps --format "{{.Names}}" | grep -E "nexusccd|db" | wc -l)
echo "   Running NexusCCD containers: $RUNNING_CONTAINERS"

docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "NAME|nexusccd" | head -5

echo ""
echo "6. Testing database connection from cron scripts..."
echo ""

# Test backup script database connection
if [ -f "$PROJECT_DIR/scripts/backup_database.sh" ]; then
    echo "   Testing backup_database.sh..."
    # Extract DB name from script
    DB_NAME_IN_SCRIPT=$(grep "DB_NAME=" "$PROJECT_DIR/scripts/backup_database.sh" | head -1 | cut -d'"' -f2)
    echo "     Script uses DB: $DB_NAME_IN_SCRIPT"
    
    if [ "$DB_NAME_IN_SCRIPT" = "nexusccd_db" ]; then
        echo "     ✓ Script uses correct database name"
    else
        echo "     ✗ Script uses different database: $DB_NAME_IN_SCRIPT"
    fi
fi

echo ""
echo "=========================================="
echo "Summary:"
echo "=========================================="

if [ "$CRONS_IN_FILE" -eq "$CRONS_INSTALLED" ]; then
    echo "✓ All crons from crontab.txt are installed"
else
    echo "⚠ Mismatch: $CRONS_IN_FILE expected, $CRONS_INSTALLED installed"
fi

if [ "$USING_PROD_COMPOSE" -gt 0 ]; then
    echo "✓ Crons explicitly use production docker-compose"
else
    echo "⚠ Crons don't explicitly specify production docker-compose"
    echo "  Recommendation: Update crons to use 'docker-compose -f docker-compose.prod.yml'"
fi

echo ""
echo "=========================================="

