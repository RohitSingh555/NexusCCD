#!/usr/bin/env python3
"""
Debug script to check column mapping for CSV upload.
"""

import pandas as pd

def debug_column_mapping():
    """Debug the column mapping logic"""
    
    # Read the CSV file
    csv_file_path = "/home/agilemorph/Desktop/fredvictor/NexusCCD/test_your_csv.csv"
    df = pd.read_csv(csv_file_path)
    
    print("=== CSV COLUMNS ===")
    for i, col in enumerate(df.columns):
        print(f"{i}: '{col}'")
    
    print("\n=== FIELD MAPPING LOGIC ===")
    
    # Replicate the field mapping logic from views.py
    field_mapping = {
        # Required fields
        'first_name': ['first name', 'firstname', 'fname', 'given name', 'First Name', 'FIRST NAME'],
        'last_name': ['last name', 'lastname', 'lname', 'surname', 'family name', 'Last Name', 'LAST NAME'],
        'email': ['e-mail', 'email address', 'e_mail'],
        'phone_number': ['phone', 'phone number', 'telephone', 'tel', 'mobile', 'cell', 'Phone', 'PHONE'],
        
        # Basic information
        'client_id': ['client id', 'clientid', 'id', 'client number', 'Client ID', 'CLIENT ID'],
        'dob': ['dob', 'date of birth', 'birthdate', 'birth date', 'dateofbirth', 'DOB', 'DOB'],
    }
    
    # Create reverse mapping from column names to standardized names
    column_mapping = {}
    df_columns_lower = [col.lower().strip() for col in df.columns]
    
    print(f"Lowercase columns: {df_columns_lower}")
    
    for standard_name, variations in field_mapping.items():
        print(f"\nChecking {standard_name}:")
        for variation in variations:
            variation_lower = variation.lower().strip()
            print(f"  - '{variation}' -> '{variation_lower}'")
            if variation_lower in df_columns_lower:
                # Find the original column name (case-sensitive)
                original_col = df.columns[df_columns_lower.index(variation_lower)]
                column_mapping[original_col] = standard_name
                print(f"    ✅ MATCHED: '{original_col}' -> '{standard_name}'")
                break
        else:
            print(f"    ❌ NO MATCH for {standard_name}")
    
    print(f"\n=== FINAL COLUMN MAPPING ===")
    for original_col, standard_name in column_mapping.items():
        print(f"'{original_col}' -> '{standard_name}'")
    
    # Check required fields
    required_fields = ['first_name', 'last_name', 'phone_number', 'dob']
    print(f"\n=== REQUIRED FIELDS CHECK ===")
    for required_field in required_fields:
        found = False
        for col in df.columns:
            if column_mapping.get(col) == required_field:
                found = True
                print(f"✅ {required_field}: Found in column '{col}'")
                break
        if not found:
            print(f"❌ {required_field}: NOT FOUND")

if __name__ == "__main__":
    debug_column_mapping()
