#!/usr/bin/env python3
"""
Test script to verify the CSV upload functionality with automatic update/create logic.
"""

import requests
import json
import time

def test_csv_upload():
    """Test the CSV upload functionality"""
    
    # Test the upload endpoint
    upload_url = "http://127.0.0.1:8000/clients/upload/process/"
    
    # Read the test CSV file
    csv_file_path = "/home/agilemorph/Desktop/fredvictor/NexusCCD/test_your_csv.csv"
    
    try:
        with open(csv_file_path, 'rb') as f:
            files = {'file': f}
            
            # Make the request
            print(f"Uploading CSV file: {csv_file_path}")
            response = requests.post(upload_url, files=files)
            
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Content: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                print("\n=== UPLOAD RESULTS ===")
                print(f"Success: {result.get('success', False)}")
                print(f"Message: {result.get('message', 'No message')}")
                
                stats = result.get('stats', {})
                print(f"\n=== STATISTICS ===")
                print(f"Total Rows: {stats.get('total_rows', 0)}")
                print(f"Created: {stats.get('created', 0)}")
                print(f"Updated: {stats.get('updated', 0)}")
                print(f"Skipped: {stats.get('skipped', 0)}")
                print(f"Duplicates Flagged: {stats.get('duplicates_flagged', 0)}")
                print(f"Errors: {stats.get('errors', 0)}")
                
                if result.get('errors'):
                    print(f"\n=== ERRORS ===")
                    for error in result['errors']:
                        print(f"- {error}")
                
                if result.get('notes'):
                    print(f"\n=== NOTES ===")
                    for note in result['notes']:
                        print(f"- {note}")
                        
                return result.get('success', False)
            else:
                print(f"Upload failed with status code: {response.status_code}")
                return False
                
    except FileNotFoundError:
        print(f"Test CSV file not found: {csv_file_path}")
        return False
    except requests.exceptions.ConnectionError:
        print("Could not connect to the server. Make sure Django is running on 127.0.0.1:8000")
        return False
    except Exception as e:
        print(f"Error during upload test: {e}")
        return False

if __name__ == "__main__":
    print("Testing CSV Upload with Automatic Update/Create Logic")
    print("=" * 60)
    
    success = test_csv_upload()
    
    if success:
        print("\n✅ Upload test completed successfully!")
        print("\nThe system should have:")
        print("1. Created new clients for Client IDs that don't exist in the database")
        print("2. Updated existing clients for Client IDs that already exist")
        print("3. Created program enrollments for 'Mental Health Services'")
    else:
        print("\n❌ Upload test failed!")
        print("Check the error messages above for details.")
