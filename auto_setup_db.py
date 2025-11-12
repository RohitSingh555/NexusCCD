#!/usr/bin/env python
"""
Auto Database Setup Script for NexusCCD
Tries to set up the database automatically or provides clear instructions.
"""
import sys
import os

try:
    import psycopg
    from psycopg import sql
except ImportError:
    print("ERROR: psycopg is not installed.")
    sys.exit(1)

def try_connect(user, password, database='postgres'):
    """Try to connect with given credentials"""
    try:
        conn = psycopg.connect(
            host='localhost',
            port='5432',
            user=user,
            password=password,
            dbname=database
        )
        return conn, True
    except Exception:
        return None, False

def setup_database():
    print("=== NexusCCD Database Auto Setup ===\n")
    
    db_config = {
        'user': 'nexusccd_user',
        'password': 'nexusccd_password',
        'database': 'nexusccd_db',
    }
    
    # First, try to connect with the expected credentials
    print("Testing connection with expected credentials...")
    conn, success = try_connect(db_config['user'], db_config['password'], db_config['database'])
    
    if success:
        print(f"✓ Successfully connected! Database is already set up.\n")
        conn.close()
        return True
    
    # Try to connect to postgres database with the user (might exist but wrong password)
    conn, success = try_connect(db_config['user'], db_config['password'], 'postgres')
    if success:
        print(f"✓ User exists! Creating database...")
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_config['database'],))
        if not cursor.fetchone():
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_config['database']))
            )
            print(f"✓ Database '{db_config['database']}' created")
        else:
            print(f"✓ Database '{db_config['database']}' already exists")
        
        cursor.close()
        conn.close()
        return True
    
    # Need superuser access - try common passwords
    print("Need superuser access to create user and database...")
    print("Trying common PostgreSQL passwords...\n")
    
    common_passwords = ['postgres', 'admin', 'password', '', 'root']
    postgres_conn = None
    
    for pwd in common_passwords:
        conn, success = try_connect('postgres', pwd, 'postgres')
        if success:
            postgres_conn = conn
            print(f"✓ Connected as postgres superuser\n")
            break
    
    if not postgres_conn:
        print("✗ Could not connect as postgres superuser automatically.")
        print("\nYou need to run the interactive setup script:")
        print("  python setup_db.py")
        print("\nOr manually create the user and database:")
        print(f"  psql -U postgres")
        print(f"  CREATE USER {db_config['user']} WITH PASSWORD '{db_config['password']}';")
        print(f"  CREATE DATABASE {db_config['database']} OWNER {db_config['user']};")
        return False
    
    # Create user and database
    postgres_conn.autocommit = True
    cursor = postgres_conn.cursor()
    
    # Check/create user
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (db_config['user'],))
    if cursor.fetchone():
        print(f"User '{db_config['user']}' exists. Updating password...")
        cursor.execute(
            sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
                sql.Identifier(db_config['user']),
                sql.Literal(db_config['password'])
            )
        )
    else:
        print(f"Creating user '{db_config['user']}'...")
        cursor.execute(
            sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                sql.Identifier(db_config['user']),
                sql.Literal(db_config['password'])
            )
        )
    print(f"✓ User '{db_config['user']}' ready\n")
    
    # Check/create database
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_config['database'],))
    if cursor.fetchone():
        print(f"Database '{db_config['database']}' exists.")
    else:
        print(f"Creating database '{db_config['database']}'...")
        cursor.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(db_config['database']),
                sql.Identifier(db_config['user'])
            )
        )
    print(f"✓ Database '{db_config['database']}' ready\n")
    
    # Grant privileges
    cursor.execute(
        sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
            sql.Identifier(db_config['database']),
            sql.Identifier(db_config['user'])
        )
    )
    
    cursor.close()
    postgres_conn.close()
    
    # Connect to new database to grant schema privileges
    postgres_conn, _ = try_connect('postgres', common_passwords[common_passwords.index(pwd)], db_config['database'])
    if postgres_conn:
        postgres_conn.autocommit = True
        cursor = postgres_conn.cursor()
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
        postgres_conn.close()
    
    # Test final connection
    conn, success = try_connect(db_config['user'], db_config['password'], db_config['database'])
    if success:
        print("=== Setup Complete! ===\n")
        print(f"User: {db_config['user']}")
        print(f"Database: {db_config['database']}")
        print(f"Password: {db_config['password']}\n")
        conn.close()
        return True
    else:
        print("✗ Setup completed but connection test failed.")
        return False

if __name__ == "__main__":
    success = setup_database()
    if success:
        print("✓ You can now run: python manage.py migrate")
    sys.exit(0 if success else 1)

