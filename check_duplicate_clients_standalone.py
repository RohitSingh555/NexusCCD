#!/usr/bin/env python
"""
Standalone script to check for duplicate client records.
Can be run outside Docker but connects to the Docker database.

Usage:
    python check_duplicate_clients_standalone.py [options]

Environment variables (optional, defaults shown):
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=nexusccd_db
    DB_USER=nexusccd_user
    DB_PASSWORD=nexusccd_password
"""

import os
import sys
from pathlib import Path

# Add the project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ccd.settings')

# Detect if running inside Docker (check for /app directory or DB_HOST env var)
# If running inside Docker, use 'db' as host, otherwise use 'localhost'
if os.path.exists('/app') or os.getenv('DB_HOST'):
    # Running inside Docker or DB_HOST is already set
    db_host = os.getenv('DB_HOST', 'db')
else:
    # Running on host machine, connect to Docker database on localhost
    db_host = 'localhost'

os.environ.setdefault('DB_HOST', db_host)
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'nexusccd_db')
os.environ.setdefault('DB_USER', 'nexusccd_user')
os.environ.setdefault('DB_PASSWORD', 'nexusccd_password')

# Import Django after setting environment
import django
django.setup()

from django.db.models import Count
from core.models import Client


def print_header(text):
    """Print a formatted header"""
    print('\n' + '=' * 80)
    print(f'🔍 {text}')
    print('=' * 80)


def print_success(text):
    """Print success message"""
    print(f'✅ {text}')


def print_warning(text):
    """Print warning message"""
    print(f'⚠️  {text}')


def print_error(text):
    """Print error message"""
    print(f'❌ {text}')


def check_name_duplicates(verbose=False, limit=50):
    """Check for duplicates based on first_name + last_name combination"""
    print_header('Checking for duplicates based on FIRST NAME + LAST NAME')
    
    # Use aggregation to find duplicates
    duplicates = (
        Client.objects
        .values('first_name', 'last_name')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .order_by('-count')
    )

    if not duplicates.exists():
        print_success('No duplicates found based on first_name + last_name')
        return 0

    total_groups = duplicates.count()
    
    print_warning(f'\nFound {total_groups} duplicate group(s) based on first_name + last_name')

    if verbose:
        print('\n📋 Details of duplicate groups:\n')
        print('-' * 80)
        
        for idx, dup in enumerate(duplicates[:limit], 1):
            first_name = dup['first_name'] or '(empty)'
            last_name = dup['last_name'] or '(empty)'
            count = dup['count']
            
            print(f"\n{idx}. {first_name} {last_name} ({count} records)")
            
            # Get all clients with this name combination
            clients = Client.objects.filter(
                first_name=dup['first_name'],
                last_name=dup['last_name']
            ).order_by('id')
            
            for client in clients:
                client_id_display = client.client_id or '(no client_id)'
                dob_display = client.dob.strftime('%Y-%m-%d') if client.dob else '(no DOB)'
                created_display = client.created_at.strftime('%Y-%m-%d %H:%M:%S')
                
                print(
                    f"   • ID: {client.id:6d} | "
                    f"client_id: {client_id_display:15s} | "
                    f"DOB: {dob_display:12s} | "
                    f"Created: {created_display}"
                )
        
        if total_groups > limit:
            print(f"\n... and {total_groups - limit} more group(s)")
        
        print('-' * 80)
    else:
        # Show summary without details
        for idx, dup in enumerate(duplicates[:limit], 1):
            first_name = dup['first_name'] or '(empty)'
            last_name = dup['last_name'] or '(empty)'
            count = dup['count']
            print(f"  {idx}. {first_name} {last_name}: {count} records")
        
        if total_groups > limit:
            print(f"  ... and {total_groups - limit} more group(s)")
        
        print_warning('\n💡 Use --verbose to see detailed information about each duplicate group')

    return total_groups


def check_client_id_duplicates(verbose=False, limit=50):
    """Check for duplicates based on client_id"""
    print_header('Checking for duplicates based on CLIENT ID')
    
    # Use aggregation to find duplicates
    duplicates = (
        Client.objects
        .exclude(client_id__isnull=True)
        .exclude(client_id='')
        .values('client_id')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .order_by('-count')
    )

    if not duplicates.exists():
        print_success('No duplicates found based on client_id')
        return 0

    total_groups = duplicates.count()
    
    print_warning(f'\nFound {total_groups} duplicate group(s) based on client_id')

    if verbose:
        print('\n📋 Details of duplicate groups:\n')
        print('-' * 80)
        
        for idx, dup in enumerate(duplicates[:limit], 1):
            client_id = dup['client_id']
            count = dup['count']
            
            print(f"\n{idx}. client_id: {client_id} ({count} records)")
            
            # Get all clients with this client_id
            clients = Client.objects.filter(
                client_id=client_id
            ).order_by('id')
            
            for client in clients:
                name_display = f"{client.first_name or '(no first name)'} {client.last_name or '(no last name)'}"
                dob_display = client.dob.strftime('%Y-%m-%d') if client.dob else '(no DOB)'
                created_display = client.created_at.strftime('%Y-%m-%d %H:%M:%S')
                
                print(
                    f"   • ID: {client.id:6d} | "
                    f"Name: {name_display:30s} | "
                    f"DOB: {dob_display:12s} | "
                    f"Created: {created_display}"
                )
        
        if total_groups > limit:
            print(f"\n... and {total_groups - limit} more group(s)")
        
        print('-' * 80)
    else:
        # Show summary without details
        for idx, dup in enumerate(duplicates[:limit], 1):
            client_id = dup['client_id']
            count = dup['count']
            print(f"  {idx}. client_id: {client_id}: {count} records")
        
        if total_groups > limit:
            print(f"  ... and {total_groups - limit} more group(s)")
        
        print_warning('\n💡 Use --verbose to see detailed information about each duplicate group')

    return total_groups


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check for duplicate client records',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check all duplicates
  python check_duplicate_clients_standalone.py
  
  # Check only name duplicates with verbose output
  python check_duplicate_clients_standalone.py --check-name --verbose
  
  # Check only client_id duplicates
  python check_duplicate_clients_standalone.py --check-client-id
  
  # Limit output to 20 groups
  python check_duplicate_clients_standalone.py --limit 20
        """
    )
    
    parser.add_argument(
        '--check-name',
        action='store_true',
        help='Check for duplicates based on first_name + last_name combination',
    )
    parser.add_argument(
        '--check-client-id',
        action='store_true',
        help='Check for duplicates based on client_id',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed output including all duplicate records',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Limit the number of duplicate groups to display (default: 50)',
    )
    
    args = parser.parse_args()
    
    check_name = args.check_name
    check_client_id = args.check_client_id
    verbose = args.verbose
    limit = args.limit
    
    # If no specific check is specified, check all by default
    if not check_name and not check_client_id:
        check_all = True
    else:
        check_all = False
    
    duplicates_found = False
    total_duplicate_records = 0
    
    # Check for duplicates based on first_name + last_name
    if check_all or check_name:
        name_duplicates = check_name_duplicates(verbose, limit)
        if name_duplicates:
            duplicates_found = True
            total_duplicate_records += name_duplicates
    
    # Check for duplicates based on client_id
    if check_all or check_client_id:
        client_id_duplicates = check_client_id_duplicates(verbose, limit)
        if client_id_duplicates:
            duplicates_found = True
            total_duplicate_records += client_id_duplicates
    
    # Summary
    print('\n' + '=' * 80)
    if duplicates_found:
        print_error(f'Found duplicate records! Total duplicate groups: {total_duplicate_records}')
    else:
        print_success('No duplicate records found based on the specified criteria.')
    print('=' * 80 + '\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print_error(f'Error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

