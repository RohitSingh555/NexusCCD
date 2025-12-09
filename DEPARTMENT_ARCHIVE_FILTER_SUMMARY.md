# Department Archive Filter - Summary of Changes

## Overview
Updated all Department queries across the codebase to exclude archived departments (`is_archived = false`). This ensures that archived test departments (Employment, Healthcare, Social Services, Test Dept) and any other archived departments are not shown in user-facing queries.

## Files Modified

### 1. **clients/views.py**
   - **Line ~235, 636, 753, 820, 972**: Updated `assigned_departments` queries for Leaders to filter `is_archived=False`
   - **Line ~3266**: Updated departments cache for uploads to filter `is_archived=False`
   - **Changes**: Added `is_archived=False` filter to all `Department.objects.filter()` calls for leader assignments

### 2. **programs/views.py**
   - **Line ~223, 271, 350, 560**: Updated `assigned_departments` queries for Leaders to filter `is_archived=False`
   - **Line ~1028, 1160**: Updated form department querysets to always filter `is_archived=False` (removed conditional check)
   - **Line ~1558**: Updated `Department.objects.get()` to filter `is_archived=False`
   - **Note**: `get_or_create` calls (lines 735, 737, 1041) are left unchanged as they're used for creating departments during imports

### 3. **core/views.py**
   - **Line ~234, 368, 679, 721, 749, 2163, 2277, 2364, 2840, 2911, 3096**: Updated all `assigned_departments` queries for Leaders to filter `is_archived=False`
   - **Line ~1506**: Updated audit log department lookup to filter `is_archived=False`
   - **Line ~1689-1697**: Updated `DepartmentListView.get_queryset()` to always filter `is_archived=False` (removed conditional check)
   - **Line ~2074**: Already had filter, verified it's correct

### 4. **reports/views.py**
   - **Line ~130, 927, 932, 1123, 1128**: Updated `available_departments` queries to filter `is_archived=False`
   - **Line ~814, 1020, 1084, 1202, 1831**: Updated `Department.objects.get()` calls to filter `is_archived=False`
   - **Line ~1746, 1750, 1752**: Updated department queries to filter `is_archived=False`

### 5. **staff/views.py**
   - **Line ~707**: Already had filter, verified it's correct

### 6. **core/models.py**
   - **Line ~145**: Updated `get_assigned_departments()` for Leaders to filter `is_archived=False`
   - **Line ~183**: Updated `get_assigned_departments()` for Program Managers to filter `is_archived=False`
   - **Line ~209**: Added `departments()` method to return assigned departments (non-archived) for compatibility

### 7. **core/security.py**
   - **Line ~155, 157**: Updated to use `staff.departments()` method instead of `staff.departments.all()`
   - **Note**: The `departments()` method now returns only non-archived departments

### 8. **core/api_views.py**
   - **Line ~321, 326**: Updated API endpoints to filter `is_archived=False` for department counts and listings

## Pattern Applied

All Department queries now follow this pattern:

**Before:**
```python
Department.objects.all()
Department.objects.filter(...)
Department.objects.get(...)
```

**After:**
```python
Department.objects.filter(is_archived=False)
Department.objects.filter(..., is_archived=False)
Department.objects.get(..., is_archived=False)
```

## Exceptions (Intentionally Left Unchanged)

1. **Management Commands**: `get_or_create` calls in management commands are left unchanged as they may need to work with archived departments
2. **Migrations**: Department queries in migrations are left unchanged as they need to access all departments
3. **Audit Log Restoration**: `Department.objects.get(external_id=...)` in audit log restoration is left unchanged as it needs to restore archived departments
4. **Upload Processing**: `get_or_create` during uploads is left unchanged as it creates departments if they don't exist

## Testing Checklist

- [ ] Department list view shows only non-archived departments
- [ ] Program creation/editing form shows only non-archived departments in dropdown
- [ ] Leader users see only their assigned non-archived departments
- [ ] Manager users see only departments from their assigned programs (non-archived)
- [ ] Reports filter by non-archived departments only
- [ ] API endpoints return only non-archived departments
- [ ] Client uploads work correctly with department creation
- [ ] Security filters work correctly with non-archived departments

## Notes

- The `departments()` method in Staff model now returns a queryset (not a property) to maintain compatibility with existing code that calls `staff.departments()`
- All user-facing queries now consistently exclude archived departments
- Admin users can still access archived departments through direct database queries if needed
