# Test Upload Files - Duplicate Detection Testing Guide

## Overview
These test CSV files are designed to test the duplicate detection functionality for SMIS and EMHware source uploads.

## Test Files

### 1. `test_smims_upload.csv` (SMIS Source)
- Contains 10 clients with SMIS client IDs (SM001-SM010)
- Use this file to test SMIS source uploads

### 2. `test_emhware_upload.csv` (EMHware Source)
- Contains 10 clients with EMHware client IDs (EM001-EM010)
- Use this file to test EMHware source uploads

## Testing Scenarios

### Scenario 1: First Upload (New Clients)
**Steps:**
1. Upload `test_smims_upload.csv` with source = **SMIS**
2. All 10 clients should be created as new clients
3. No duplicates should be flagged

**Expected Result:**
- 10 clients created
- 0 duplicates flagged

### Scenario 2: Duplicate Detection (Name-Based Matching)
**Steps:**
1. After Scenario 1, upload `test_emhware_upload.csv` with source = **EMHware**
2. The following clients have similar names to SMIS clients:
   - EM001: "Jon Smith" (similar to SM001: "John Smith")
   - EM002: "Mike Brown" (similar to SM002: "Michael Brown")
   - EM003: "Jennifer Williams" (exact match with SM003)
   - EM004: "Robert Johnson" (exact match with SM004)

**Expected Result:**
- 4 duplicates should be flagged (name-based matching)
- 6 new clients should be created
- ClientDuplicate records should be created for the 4 matches

### Scenario 3: Update Existing Client (ID Match)
**Steps:**
1. Upload `test_smims_upload.csv` again with source = **SMIS**
2. Modify some data in the CSV (e.g., change John Smith's email)
3. Upload the modified file

**Expected Result:**
- All 10 clients should be **updated** (not created)
- Client ID + Source combination matches existing records
- No duplicates flagged (they're updates, not new clients)

### Scenario 4: Cross-Source Duplicate Detection
**Steps:**
1. Upload a new CSV with SMIS source containing:
   - Client ID: SM011
   - First Name: "Patricia"
   - Last Name: "Moore"
   - This should match EM005 from EMHware upload

**Expected Result:**
- Client should be created
- Duplicate should be flagged (Patricia Moore from EMHware)
- ClientDuplicate record created linking SM011 to EM005

## Test File Structure

### Required Fields:
- **Client ID** (required for all uploads)
- **First Name** (required for new clients)
- **Last Name** (required for new clients)
- **Either Phone OR Date of Birth** (required for new clients)

### Optional Fields:
- Email
- Gender
- Address, City, Province, Postal Code
- Other demographic fields

## Notes

1. **Name Similarity Threshold**: The system uses a 0.7 similarity threshold for name-based duplicate detection
   - "John" vs "Jon" = high similarity (will match)
   - "Michael" vs "Mike" = high similarity (will match)
   - Exact matches = 100% similarity (will match)

2. **Source-Specific Logic**: 
   - SMIS and EMHware sources check for name duplicates when no ID match is found
   - Other sources use email/phone-based duplicate detection

3. **Duplicate Review**: 
   - All flagged duplicates appear in the "Probable Duplicate Clients" page
   - Reviewers can mark as "Not Duplicate", "Confirmed Duplicate", or "Merge"

## Testing Checklist

- [ ] Upload SMIS file - all clients created successfully
- [ ] Upload EMHware file - name duplicates detected and flagged
- [ ] Check ClientDuplicate records created correctly
- [ ] Re-upload SMIS file - existing clients updated (not duplicated)
- [ ] Verify similarity scores are calculated correctly
- [ ] Check duplicate review page shows all flagged duplicates

