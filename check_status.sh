#!/bin/bash
echo "=== Container Status ==="
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "=== Web Service Logs (last 30 lines) ==="
docker-compose -f docker-compose.prod.yml logs web --tail=30

echo ""
echo "=== Nginx Logs (last 20 lines) ==="
docker-compose -f docker-compose.prod.yml logs nginx --tail=20

echo ""
echo "=== Database Status ==="
docker-compose -f docker-compose.prod.yml exec db pg_isready -U nexusccd_user -d nexusccd_db

echo ""
echo "=== Testing Web Service ==="
docker-compose -f docker-compose.prod.yml exec web curl -I http://localhost:8000 2>&1 | head -5

echo ""
echo "=== Testing from Nginx ==="
docker-compose -f docker-compose.prod.yml exec nginx wget -O- -T 2 http://web:8000 2>&1 | head -5



