-- SQL Query to Archive Test Departments
-- This query sets is_archived = true and archived_at = current timestamp
-- for the following test departments:
--   - Employment
--   - Healthcare
--   - Social Services
--   - Test Dept

UPDATE departments
SET 
    is_archived = true,
    archived_at = NOW()
WHERE 
    name IN ('Employment', 'Healthcare', 'Social Services', 'Test Dept')
    AND is_archived = false;

-- Optional: Verify the update
-- SELECT id, name, is_archived, archived_at 
-- FROM departments 
-- WHERE name IN ('Employment', 'Healthcare', 'Social Services', 'Test Dept');
