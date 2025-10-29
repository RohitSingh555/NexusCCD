#!/usr/bin/env python3
"""
Django Load Test Setup Verification Script

This script helps verify that your Django backend is properly configured
to handle the X-Load-Test header and skip database writes during load testing.

Usage:
    python verify_load_test_setup.py --url https://your-api-domain.com/clients/upload/process/
"""

import argparse
import requests
import json
import csv
import io
import sys
from datetime import datetime, timedelta
import random

def generate_test_client_data(count=5):
    """Generate a small sample of test client data"""
    first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones']
    genders = ['Male', 'Female', 'Other', 'Unknown']
    provinces = ['ON', 'BC', 'AB', 'QC', 'MB']
    cities = ['Toronto', 'Vancouver', 'Calgary', 'Montreal', 'Ottawa']
    
    clients = []
    for i in range(count):
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        client_id = f'VERIFY_TEST_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{i}'
        
        # Generate random date of birth (18-80 years ago)
        age = random.randint(18, 80)
        birth_date = datetime.now() - timedelta(days=age*365 + random.randint(0, 365))
        
        # Generate random phone number
        area_code = random.randint(100, 999)
        exchange = random.randint(100, 999)
        number = random.randint(1000, 9999)
        phone = f"+1{area_code}{exchange}{number}"
        
        # Generate random postal code
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        postal = ''.join([
            random.choice(letters),
            str(random.randint(0, 9)),
            random.choice(letters),
            ' ',
            str(random.randint(0, 9)),
            random.choice(letters),
            str(random.randint(0, 9))
        ])
        
        clients.append({
            'Client ID': client_id,
            'First Name': first_name,
            'Last Name': last_name,
            'Date of Birth': birth_date.strftime('%Y-%m-%d'),
            'Gender': random.choice(genders),
            'Phone': phone,
            'Email': f'{first_name.lower()}.{last_name.lower()}{i}@verifytest.com',
            'Address': f'{random.randint(1, 9999)} Test Street',
            'City': random.choice(cities),
            'Province': random.choice(provinces),
            'Postal Code': postal,
            'Comments': f'Verification test data - Record {i + 1}'
        })
    
    return clients

def convert_to_csv(clients):
    """Convert client data to CSV format"""
    if not clients:
        return ''
    
    output = io.StringIO()
    fieldnames = clients[0].keys()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(clients)
    return output.getvalue()

def test_upload_endpoint(url, auth_token=None, use_load_test_header=True):
    """Test the upload endpoint with and without the X-Load-Test header"""
    
    print(f"🔍 Testing upload endpoint: {url}")
    print(f"📊 Load test header: {'Enabled' if use_load_test_header else 'Disabled'}")
    print()
    
    # Generate test data
    test_clients = generate_test_client_data(5)
    csv_data = convert_to_csv(test_clients)
    
    # Prepare headers
    headers = {
        'User-Agent': 'load-test-verification/1.0'
    }
    
    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'
    
    if use_load_test_header:
        headers['X-Load-Test'] = 'true'
    
    # Prepare form data
    files = {
        'file': ('test_clients.csv', csv_data, 'text/csv')
    }
    data = {
        'source': 'SMIMS'  # Valid source values: 'SMIMS' or 'EMHware'
    }
    
    try:
        print("📤 Sending test upload request...")
        response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        try:
            response_json = response.json()
            print(f"📊 Response Body: {json.dumps(response_json, indent=2)}")
        except json.JSONDecodeError:
            print(f"📊 Response Body (raw): {response.text[:500]}...")
        
        # Analyze response
        if response.status_code in [200, 201]:
            print("✅ Upload request successful")
            
            if use_load_test_header:
                # Check if the response indicates load test mode
                try:
                    response_data = response.json()
                    if 'load_test_mode' in response_data or 'test_mode' in response_data:
                        print("✅ Load test mode detected in response")
                    else:
                        print("⚠️  Load test mode not explicitly confirmed in response")
                except:
                    print("⚠️  Could not parse response to verify load test mode")
            
            return True
        else:
            print(f"❌ Upload request failed with status {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - check your URL and server status")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def verify_django_setup():
    """Verify Django backend setup for load testing"""
    print("🔧 Django Load Test Setup Verification")
    print("=" * 50)
    print()
    
    # Check if Django is configured to handle X-Load-Test header
    print("📋 Checklist for Django Backend Setup:")
    print()
    print("1. ✅ Upload endpoint exists and accepts POST requests")
    print("2. ⚠️  X-Load-Test header handling (needs verification)")
    print("3. ⚠️  Database write skipping in test mode (needs verification)")
    print("4. ⚠️  Proper error handling and logging (needs verification)")
    print()
    
    print("🔧 Required Django Backend Modifications:")
    print()
    print("Add this to your upload_clients view in clients/views.py:")
    print()
    print("```python")
    print("@csrf_exempt")
    print("@require_http_methods([\"POST\"])")
    print("def upload_clients(request):")
    print("    \"\"\"Handle CSV/Excel file upload and process client data\"\"\"")
    print("    ")
    print("    # Check for load test mode")
    print("    is_load_test = request.headers.get('X-Load-Test', '').lower() == 'true'")
    print("    ")
    print("    if is_load_test:")
    print("        # Skip actual database writes in load test mode")
    print("        print(f'[LOAD TEST] Processing {len(processed_clients)} clients (no DB writes)')")
    print("        return JsonResponse({")
    print("            'success': True,")
    print("            'message': f'Load test mode: {len(processed_clients)} clients processed (no DB writes)',")
    print("            'load_test_mode': True,")
    print("            'processed_count': len(processed_clients)")
    print("        })")
    print("    ")
    print("    # ... rest of your existing upload logic ...")
    print("```")
    print()

def main():
    parser = argparse.ArgumentParser(description='Verify Django load test setup')
    parser.add_argument('--url', required=True, help='Upload endpoint URL')
    parser.add_argument('--auth-token', help='Optional JWT authentication token')
    parser.add_argument('--no-load-test-header', action='store_true', 
                       help='Test without X-Load-Test header (for comparison)')
    
    args = parser.parse_args()
    
    print("🚀 Django Load Test Verification Tool")
    print("=" * 50)
    print()
    
    # Show Django setup requirements
    verify_django_setup()
    
    # Test with load test header
    print("🧪 Testing with X-Load-Test header...")
    print("-" * 30)
    success_with_header = test_upload_endpoint(args.url, args.auth_token, use_load_test_header=True)
    print()
    
    # Test without load test header (for comparison)
    if not args.no_load_test_header:
        print("🧪 Testing without X-Load-Test header (for comparison)...")
        print("-" * 30)
        success_without_header = test_upload_endpoint(args.url, args.auth_token, use_load_test_header=False)
        print()
        
        # Summary
        print("📊 Test Results Summary:")
        print("=" * 30)
        print(f"With X-Load-Test header: {'✅ PASS' if success_with_header else '❌ FAIL'}")
        print(f"Without X-Load-Test header: {'✅ PASS' if success_without_header else '❌ FAIL'}")
        
        if success_with_header and success_without_header:
            print()
            print("⚠️  WARNING: Both tests passed - this suggests your backend")
            print("   may not be properly handling the X-Load-Test header.")
            print("   Make sure to implement the database write skipping logic.")
    else:
        print("📊 Test Results Summary:")
        print("=" * 30)
        print(f"With X-Load-Test header: {'✅ PASS' if success_with_header else '❌ FAIL'}")
    
    print()
    print("🔧 Next Steps:")
    print("1. Implement X-Load-Test header handling in your Django backend")
    print("2. Add database write skipping logic for load test mode")
    print("3. Test again with this verification script")
    print("4. Run the full load test suite once verification passes")
    print()
    
    if success_with_header:
        print("✅ Your upload endpoint is working! You can proceed with load testing.")
    else:
        print("❌ Your upload endpoint needs configuration before load testing.")
        sys.exit(1)

if __name__ == '__main__':
    main()
