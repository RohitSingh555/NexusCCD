#!/usr/bin/env python
"""
Database Setup Script for NexusCCD
This script will create the database user and database if they don't exist.
You'll need the PostgreSQL superuser (postgres) password.
"""
import getpass
import sys
import os

try:
    import psycopg
    from psycopg import sql
    # Use psycopg2-compatible interface
    psycopg2 = psycopg
except ImportError:
    try:
        import psycopg2
        from psycopg2 import sql
    except ImportError:
        print("ERROR: psycopg or psycopg2 is not installed.")
        print("Install it with: pip install psycopg2-binary")
        sys.exit(1)

def setup_database():
    print("=== NexusCCD Database Setup ===\n")
    
    # Get PostgreSQL superuser password
    print("Enter PostgreSQL superuser (postgres) password:")
    postgres_password = getpass.getpass("Password: ")
    
    # Database configuration
    db_config = {
        'user': 'nexusccd_user',
        'password': 'nexusccd_password',
        'database': 'nexusccd_db',
        'host': 'localhost',
        'port': '5432'
    }
    
    try:
        # Connect as postgres superuser
        print("\nConnecting to PostgreSQL as superuser...")
        try:
            # Try psycopg (newer version)
            conn = psycopg.connect(
                host='localhost',
                port='5432',
                user='postgres',
                password=postgres_password,
                dbname='postgres'
            )
        except (NameError, AttributeError):
            # Fall back to psycopg2
            conn = psycopg2.connect(
                host='localhost',
                port='5432',
                user='postgres',
                password=postgres_password,
                database='postgres'
            )
        conn.autocommit = True
        cursor = conn.cursor()
        print("✓ Connected successfully\n")
        
        # Check if user exists
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (db_config['user'],))
        user_exists = cursor.fetchone()
        
        if user_exists:
            print(f"User '{db_config['user']}' already exists. Updating password...")
            cursor.execute(
                sql.SQL("ALTER USER {} WITH PASSWORD %s").format(
                    sql.Identifier(db_config['user'])
                ),
                (db_config['password'],)
            )
            print(f"✓ Password updated for user '{db_config['user']}'\n")
        else:
            print(f"Creating user '{db_config['user']}'...")
            cursor.execute(
                sql.SQL("CREATE USER {} WITH PASSWORD %s").format(
                    sql.Identifier(db_config['user'])
                ),
                (db_config['password'],)
            )
            print(f"✓ User '{db_config['user']}' created\n")
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_config['database'],))
        db_exists = cursor.fetchone()
        
        if db_exists:
            print(f"Database '{db_config['database']}' already exists.")
            # Grant privileges anyway
            cursor.execute(
                sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
                    sql.Identifier(db_config['database']),
                    sql.Identifier(db_config['user'])
                )
            )
            print(f"✓ Privileges granted to '{db_config['user']}'\n")
        else:
            print(f"Creating database '{db_config['database']}'...")
            cursor.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(db_config['database']),
                    sql.Identifier(db_config['user'])
                )
            )
            print(f"✓ Database '{db_config['database']}' created\n")
        
        # Connect to the new database to grant schema privileges
        cursor.close()
        conn.close()
        
        try:
            conn = psycopg.connect(
                host='localhost',
                port='5432',
                user='postgres',
                password=postgres_password,
                dbname=db_config['database']
            )
        except (NameError, AttributeError):
            conn = psycopg2.connect(
                host='localhost',
                port='5432',
                user='postgres',
                password=postgres_password,
                database=db_config['database']
            )
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute(
            sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(
                sql.Identifier(db_config['user'])
            )
        )
        cursor.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}").format(
                sql.Identifier(db_config['user'])
            )
        )
        cursor.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {}").format(
                sql.Identifier(db_config['user'])
            )
        )
        
        cursor.close()
        conn.close()
        
        print("=== Setup Complete! ===\n")
        print(f"User: {db_config['user']}")
        print(f"Database: {db_config['database']}")
        print(f"Password: {db_config['password']}\n")
        print("You can now run: python manage.py migrate")
        return True
        
    except (psycopg.OperationalError, psycopg2.OperationalError) as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nPossible issues:")
        print("1. PostgreSQL service is not running")
        print("2. Wrong password for postgres user")
        print("3. PostgreSQL is not listening on localhost:5432")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False

if __name__ == "__main__":
    success = setup_database()
    sys.exit(0 if success else 1)

