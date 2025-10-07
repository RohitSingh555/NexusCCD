#!/usr/bin/env python
import os
import django
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ccd.settings')
django.setup()

from django.db import connection

def fix_migration():
    cursor = connection.cursor()
    
    try:
        # Check if migration 0016 is already recorded
        cursor.execute("""
            SELECT COUNT(*) FROM django_migrations 
            WHERE app = 'core' AND name = '0016_add_updated_by_to_client'
        """)
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Insert the missing migration record
            cursor.execute("""
                INSERT INTO django_migrations (app, name, applied) 
                VALUES ('core', '0016_add_updated_by_to_client', %s)
            """, [datetime.now()])
            print("✅ Migration 0016 marked as applied")
        else:
            print("✅ Migration 0016 already exists")
            
        # Now try to run migrations
        from django.core.management import execute_from_command_line
        execute_from_command_line(['manage.py', 'migrate'])
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cursor.close()

if __name__ == "__main__":
    fix_migration()
