# Docker Commands Help - NexusCCD Django Application

## 🐳 Basic Docker Commands

### Container Management
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d db
docker-compose up -d web
docker-compose up -d redis

# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down --volumes

# Restart services
docker-compose restart

# Restart specific service
docker-compose restart web
```

### Viewing Logs
```bash
# View all logs
docker-compose logs

# View logs for specific service
docker-compose logs web
docker-compose logs db
docker-compose logs redis

# Follow logs in real-time
docker-compose logs -f web

# View last 100 lines of logs
docker-compose logs --tail=100 web

# View logs with timestamps
docker-compose logs -t web
```

### Container Status
```bash
# Check container status
docker-compose ps

# Check running containers
docker ps

# Check all containers (including stopped)
docker ps -a

# View container details
docker inspect nexusccd_web_1
```

## 🗄️ Database Operations

### Migrations
```bash
# Run migrations
docker-compose run --rm web python manage.py migrate

# Create new migration
docker-compose run --rm web python manage.py makemigrations

# Show migration status
docker-compose run --rm web python manage.py showmigrations

# Rollback specific migration
docker-compose run --rm web python manage.py migrate app_name migration_number
```

### Database Access
```bash
# Access PostgreSQL shell
docker-compose exec db psql -U nexusccd_user -d nexusccd_db

# Create database backup
docker-compose exec db pg_dump -U nexusccd_user nexusccd_db > backup.sql

# Restore database from backup
docker-compose exec -T db psql -U nexusccd_user -d nexusccd_db < backup.sql
```

## 🚀 Django Management Commands

### Static Files
```bash
# Collect static files
docker-compose run --rm web python manage.py collectstatic --noinput

# Collect static files with confirmation
docker-compose run --rm web python manage.py collectstatic
```

### User Management
```bash
# Create superuser
docker-compose run --rm web python manage.py createsuperuser

# Setup initial data (roles, departments, users)
docker-compose run --rm web python manage.py setup_initial_data
```

### Data Management
```bash
# Delete all client and enrollment data
docker-compose exec web python manage.py shell -c "
from core.models import Client, ClientProgramEnrollment;
ClientProgramEnrollment.objects.all().delete();
Client.objects.all().delete();
print('Client data deleted successfully');
"

# Check data counts
docker-compose exec web python manage.py shell -c "
from core.models import Client, ClientProgramEnrollment;
print(f'Clients: {Client.objects.count()}');
print(f'Enrollments: {ClientProgramEnrollment.objects.count()}');
"

# Delete specific client data types
docker-compose exec web python manage.py shell -c "
from core.models import ClientDuplicate, ClientExtended;
ClientDuplicate.objects.all().delete();
ClientExtended.objects.all().delete();
print('Additional client data deleted');
"
```

### Program Management
```bash
# Delete test programs created on Nov 3 (preview)
docker-compose run --rm web python manage.py delete_test_programs --date 2024-11-03 --dry-run

# Delete test programs created on Nov 3 (actually delete - requires confirmation)
docker-compose run --rm web python manage.py delete_test_programs --date 2024-11-03 --confirm

# Delete programs from specific date
docker-compose run --rm web python manage.py delete_test_programs --date 2024-11-03 --dry-run

# Import programs from CSV
docker-compose run --rm web python manage.py import_programs /path/to/programs.csv

# Check program counts
docker-compose exec web python manage.py shell -c "
from core.models import Program;
print(f'Total Programs: {Program.objects.count()}');
print(f'Active Programs: {Program.objects.filter(status=\"active\").count()}');
print(f'Suggested Programs: {Program.objects.filter(status=\"suggested\").count()}');
"
```

### Audit Log Management
```bash
# Cleanup old audit logs (default: 15 days)
docker-compose exec web python manage.py cleanup_old_audit_logs

# Cleanup delete records older than 7 days (automatically included in scheduled cleanup)
docker-compose exec web python manage.py cleanup_old_audit_logs --cleanup-deletes --delete-days 7

# Cleanup both delete records (7 days) and other records (15 days)
docker-compose exec web python manage.py cleanup_old_audit_logs --cleanup-deletes --delete-days 7 --days 15

# Cleanup with custom retention period (e.g., 30 days)
docker-compose exec web python manage.py cleanup_old_audit_logs --days 30

# Preview what would be deleted (dry run)
docker-compose exec web python manage.py cleanup_old_audit_logs --cleanup-deletes --dry-run --verbose

# Run cleanup script (for cron/scheduled tasks - automatically cleans delete records)
./scripts/cleanup_old_audit_logs.sh
```

### Data Cleanup Commands
```bash
# Delete programs, services, and enrollments created after October 31st
# Preview what would be deleted (dry run)
docker-compose exec web python manage.py delete_post_oct31_data --year 2024 --dry-run

# Delete records created after Oct 31, 2024 (requires confirmation)
docker-compose exec web python manage.py delete_post_oct31_data --year 2024 --confirm

# Delete with audit logging
docker-compose exec web python manage.py delete_post_oct31_data --year 2024 --confirm --create-audit-logs
```

### Development Commands
```bash
# Django shell
docker-compose run --rm web python manage.py shell

# Run tests
docker-compose run --rm web python manage.py test

# Check Django configuration
docker-compose run --rm web python manage.py check

# Show URLs
docker-compose run --rm web python manage.py show_urls
```

## 🔧 Maintenance Commands

### Cleanup
```bash
# Remove unused containers, networks, images
docker system prune

# Remove all unused data (WARNING: aggressive cleanup)
docker system prune -a

# Remove specific container
docker rm container_name

# Remove specific image
docker rmi image_name
```

### Volume Management
```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect nexusccd_postgres_data

# Remove specific volume
docker volume rm volume_name

# Remove all unused volumes
docker volume prune
```

### Image Management
```bash
# List images
docker images

# Build image
docker-compose build

# Build specific service
docker-compose build web

# Pull latest images
docker-compose pull
```

## 🐛 Debugging Commands

### Container Access
```bash
# Access web container shell
docker-compose exec web bash

# Access database container shell
docker-compose exec db bash

# Run one-time command in container
docker-compose run --rm web python manage.py shell
```

### Health Checks
```bash
# Check if services are healthy
docker-compose ps

# Check container health
docker inspect --format='{{.State.Health.Status}}' nexusccd_db_1

# Test database connection
docker-compose exec web python manage.py dbshell
```

### Network Debugging
```bash
# List networks
docker network ls

# Inspect network
docker network inspect nexusccd_default

# Test connectivity between containers
docker-compose exec web ping db
```

## 📊 Monitoring Commands

### Resource Usage
```bash
# View container resource usage
docker stats

# View specific container stats
docker stats nexusccd_web_1

# View container processes
docker-compose exec web ps aux
```

### Log Analysis
```bash
# Search logs for specific text
docker-compose logs web | grep "ERROR"

# Count log entries
docker-compose logs web | wc -l

# Export logs to file
docker-compose logs web > web_logs.txt
```

## 🚨 Emergency Commands

### Quick Recovery
```bash
# Restart everything
docker-compose down && docker-compose up -d

# Force recreate containers
docker-compose up -d --force-recreate

# Reset to clean state (WARNING: deletes all data)
docker-compose down --volumes --remove-orphans
docker-compose up -d
```

### Backup & Restore
```bash
# Full backup (database + volumes)
docker-compose exec db pg_dump -U nexusccd_user nexusccd_db > full_backup.sql
docker-compose exec web tar -czf static_backup.tar.gz /app/staticfiles

# Quick restore
docker-compose exec -T db psql -U nexusccd_user -d nexusccd_db < full_backup.sql

# Backup with timestamp
docker-compose exec db pg_dump -U nexusccd_user nexusccd_db | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Restore from compressed backup
gunzip -c backup.sql.gz | docker-compose exec -T db psql -U nexusccd_user -d nexusccd_db
```

## 📝 Environment Variables

### Development Environment
```bash
# Set environment variables
export ENVIRONMENT=development
export DEBUG=True
export DB_PASSWORD=your_password

# Load from .env file
docker-compose --env-file .env.dev up -d
```

## 🔍 Useful One-Liners

```bash
# Quick status check
docker-compose ps && echo "App URL: http://localhost:8001"

# View recent errors
docker-compose logs --tail=50 web | grep -i error

# Restart just the web service
docker-compose restart web

# Check if app is responding
curl -I http://localhost:8001

# View database size
docker-compose exec db psql -U nexusccd_user -d nexusccd_db -c "SELECT pg_size_pretty(pg_database_size('nexusccd_db'));"

# View container resource usage
docker stats --no-stream

# Execute command in web container
docker-compose exec web bash -c "command_here"

# View all images
docker images | grep nexusccd

# Remove all stopped containers
docker container prune -f

# View network connections
docker network inspect nexusccd_default | grep -A 5 "Containers"
```

## 📋 Common Workflows

### Daily Development
```bash
# Start development environment
docker-compose up -d

# Check logs
docker-compose logs -f web

# Run migrations if needed
docker-compose run --rm web python manage.py migrate

# Stop when done
docker-compose down
```

### Production Deployment
```bash
# Pull latest changes
git pull

# Build and start
docker-compose up -d --build

# Run migrations
docker-compose run --rm web python manage.py migrate

# Collect static files
docker-compose run --rm web python manage.py collectstatic --noinput

# Verify deployment
curl -I http://localhost:8001
```

---

## 🆘 Troubleshooting

### Common Issues
1. **Port already in use**: Change ports in docker-compose.yml
2. **Database connection failed**: Check if db container is healthy
3. **Permission denied**: Check file permissions and ownership
4. **Out of disk space**: Run `docker system prune -a`

### Getting Help
```bash
# Docker help
docker --help
docker-compose --help

# Container help
docker-compose exec web python manage.py help
```

---

## ⏰ Scheduled Tasks / Cron Jobs

### Currently Configured Cron Jobs

The system has 4 automated cron jobs configured:

1. **Database Backup** - Daily at 1:00 AM
   - Creates a compressed backup of the PostgreSQL database
   - Replaces the previous backup (only keeps latest)
   - Location: `/home/Admin0/NexusCCD/backups/database_backup.sql.gz`

2. **Audit Log Cleanup** - Daily at 2:00 AM
   - Deletes delete audit log entries older than 7 days
   - Deletes other audit logs older than 15 days
   - Command: `docker-compose exec -T web python manage.py cleanup_old_audit_logs --cleanup-deletes --delete-days 7 --days 15`

3. **Daily Client Report** - Daily at 11:00 PM
   - Sends daily client reports via email
   - Script: `/home/Admin0/NexusCCD/scripts/send_daily_report.sh`

4. **Session Cleanup** - Weekly on Sunday at 3:00 AM
   - Removes expired Django sessions
   - Command: `docker-compose exec -T web python manage.py clearsessions`

### Viewing Cron Jobs

```bash
# View all configured cron jobs
crontab -l

# Edit cron jobs
crontab -e
```

### Backup Management

```bash
# Manual database backup
/home/Admin0/NexusCCD/scripts/backup_database.sh

# View backup file
ls -lh /home/Admin0/NexusCCD/backups/

# Restore from backup (if needed)
gunzip -c /home/Admin0/NexusCCD/backups/database_backup.sql.gz | docker-compose exec -T db psql -U nexusccd_user -d nexusccd_db

# View backup logs
tail -f /home/Admin0/NexusCCD/logs/database_backup.log
```

### Other Scheduled Tasks (Optional)

You can add additional maintenance tasks:
```bash
# Example: Run migrations daily at 3 AM
0 3 * * * cd /home/Admin0/NexusCCD && docker-compose exec -T web python manage.py migrate >> /home/Admin0/NexusCCD/logs/migrations.log 2>&1
```

## 🔍 Duplicate Client Check Commands

### Check for Duplicate Clients

The `check_duplicate_clients_standalone.py` script checks for duplicate client records based on:
- **First Name + Last Name** combination
- **Client ID** values

**Basic Usage (Check All Duplicates):**
```bash
docker-compose -f docker-compose.prod.yml run --rm -v $(pwd):/app web python /app/check_duplicate_clients_standalone.py --verbose
```

**Check Only Name Duplicates:**
```bash
docker-compose -f docker-compose.prod.yml run --rm -v $(pwd):/app web python /app/check_duplicate_clients_standalone.py --check-name --verbose
```

**Check Only Client ID Duplicates:**
```bash
docker-compose -f docker-compose.prod.yml run --rm -v $(pwd):/app web python /app/check_duplicate_clients_standalone.py --check-client-id --verbose
```

**Limit Output to First N Groups:**
```bash
docker-compose -f docker-compose.prod.yml run --rm -v $(pwd):/app web python /app/check_duplicate_clients_standalone.py --limit 20 --verbose
```

**Quick Check (Summary Only):**
```bash
docker-compose -f docker-compose.prod.yml run --rm -v $(pwd):/app web python /app/check_duplicate_clients_standalone.py
```

### Script Options

- `--check-name`: Check for duplicates based on first_name + last_name combination
- `--check-client-id`: Check for duplicates based on client_id
- `--verbose`: Show detailed output including all duplicate records
- `--limit N`: Limit the number of duplicate groups to display (default: 50)

### Example Output

The script will show:
- Total number of duplicate groups found
- For each duplicate group:
  - Client IDs
  - Names
  - Date of Birth
  - Creation dates
- Summary of all duplicates

**Note:** The script automatically detects if it's running inside Docker and uses the correct database host (`db` inside Docker, `localhost` on host).

---
*Last updated: $(date)*
*Application: NexusCCD Django*
*Docker Compose Version: 3.9*
