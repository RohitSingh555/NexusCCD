# Complete Database Schema Documentation - NexusCCD

This document provides a comprehensive overview of all database tables in the NexusCCD project, including their final schemas and complete migration history.

**Last Updated:** 2025-11-18  
**Django Version:** 4.2.7  
**Database:** PostgreSQL

---

## Table of Contents

### Core App Tables
1. [users](#users)
2. [departments](#departments)
3. [roles](#roles)
4. [staff](#staff)
5. [staff_roles](#staff_roles)
6. [programs](#programs)
7. [subprograms](#subprograms)
8. [program_staff](#program_staff)
9. [clients](#clients)
10. [client_extended](#client_extended)
11. [client_program_enrollments](#client_program_enrollments)
12. [intakes](#intakes)
13. [discharges](#discharges)
14. [service_restrictions](#service_restrictions)
15. [audit_logs](#audit_logs)
16. [client_duplicates](#client_duplicates)
17. [program_manager_assignments](#program_manager_assignments)
18. [program_service_manager_assignments](#program_service_manager_assignments)
19. [department_leader_assignments](#department_leader_assignments)
20. [email_recipients](#email_recipients)
21. [service_restriction_notification_subscriptions](#service_restriction_notification_subscriptions)
22. [notifications](#notifications)
23. [email_logs](#email_logs)
24. [client_upload_logs](#client_upload_logs)
25. [pending_changes](#pending_changes)

### Clients App Tables
26. [client_notes](#client_notes) *(Currently removed, models defined)*
27. [client_contacts](#client_contacts) *(Currently removed, models defined)*

### Programs App Tables
28. [program_capacities](#program_capacities)
29. [program_locations](#program_locations)
30. [program_services](#program_services)

### Staff App Tables
31. [staff_schedules](#staff_schedules)
32. [staff_notes](#staff_notes)
33. [staff_permissions](#staff_permissions)
34. [staff_client_assignments](#staff_client_assignments)
35. [staff_program_assignments](#staff_program_assignments)

### Reports App Tables
36. [report_templates](#report_templates)
37. [report_executions](#report_executions)

---

## Core App Tables

### users

**Table Name:** `users`  
**Model:** `core.User`  
**Description:** Custom user model extending Django's AbstractUser for authentication and user management.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `password` | CharField(128) | NOT NULL | - | Hashed password |
| `last_login` | DateTimeField | Nullable | NULL | Last login timestamp |
| `is_superuser` | BooleanField | NOT NULL | False | Superuser status |
| `is_staff` | BooleanField | NOT NULL | False | Staff/admin status |
| `date_joined` | DateTimeField | NOT NULL | `timezone.now()` | Account creation date |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `email` | EmailField | Unique, Indexed, NOT NULL | - | User email (used for login) |
| `username` | CharField(150) | Unique, Indexed, NOT NULL | - | Username |
| `first_name` | CharField(150) | NOT NULL | - | First name |
| `last_name` | CharField(150) | NOT NULL | - | Last name |
| `profile_photo` | ImageField | Nullable, Blank | NULL | Profile photo image |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Account active status |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `email`, `username`
- Indexed: `email`, `username`, `is_active`

**Relationships:**
- One-to-One with `Staff` via `staff_profile`
- Many-to-Many with `auth.Group` (Django groups)
- Many-to-Many with `auth.Permission` (Django permissions)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created User model with: `id`, `password`, `last_login`, `is_superuser`, `is_staff`, `date_joined`, `external_id`, `email`, `username`, `first_name`, `last_name`, `is_active`, `created_at`, `updated_at`
  - Added indexes: `email`, `username`, `is_active`
  - Added Many-to-Many relationships: `groups`, `user_permissions`

- **0007_user_profile_photo.py**
  - Added `profile_photo` field (ImageField, nullable)

---

### departments

**Table Name:** `departments`  
**Model:** `core.Department`  
**Description:** Organizational departments within the agency.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `name` | CharField(255) | Unique, Indexed, NOT NULL | - | Department name |
| `owner` | ForeignKey(Staff) | Nullable, SET_NULL | NULL | Department leader/owner |
| `is_archived` | BooleanField | Indexed, NOT NULL | False | Whether archived |
| `archived_at` | DateTimeField | Nullable, Indexed | NULL | Archive timestamp |

**Constraints:**
- Unique Constraint: `unique_lowercase_name` on `name` (where name IS NOT NULL)

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `name`
- Indexed: `name`, `is_archived`, `archived_at`, `owner_id`

**Relationships:**
- Foreign Key: `owner` → `Staff` (SET_NULL on delete)
- Reverse: `owned_departments` from Staff
- Reverse: `leader_assignments` from DepartmentLeaderAssignment
- Reverse: `program_set` from Program

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Department model with: `id`, `external_id`, `created_at`, `updated_at`, `name`, `owner` (CharField)
  - Added unique constraint: `unique_lowercase_name` on `name`

- **0044_add_department_leader_assignment.py** (2025-10-14)
  - Created `DepartmentLeaderAssignment` model (related model, not a field change)

- **0062_update_department_owner_to_foreignkey.py** (2025-10-29)
  - **Changed `owner` from CharField to ForeignKey(Staff)**
  - Migrated existing string owner values to Staff foreign keys
  - Set to NULL if no matching Staff found

- **0065_client_archived_at_client_is_archived_and_more.py** (2025-11-05)
  - **Added `is_archived`** (BooleanField, default=False, indexed)
  - **Added `archived_at`** (DateTimeField, nullable, indexed)

---

### roles

**Table Name:** `roles`  
**Model:** `core.Role`  
**Description:** User roles defining permissions and access levels.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `name` | CharField(100) | Unique, Indexed, NOT NULL | - | Role name |
| `description` | TextField | Nullable | NULL | Role description |
| `permissions` | JSONField | NOT NULL | `[]` | List of permissions |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `name`
- Indexed: `name`

**Relationships:**
- Reverse: `staffrole_set` from StaffRole

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Role model with: `id`, `external_id`, `created_at`, `updated_at`, `name`, `description`, `permissions`

- **0042_add_role_hierarchy_fields.py**
  - Added role hierarchy fields (later removed)

- **0043_alter_role_options_remove_role_can_assign_roles_and_more.py**
  - Removed role hierarchy fields and related options

---

### staff

**Table Name:** `staff`  
**Model:** `core.Staff`  
**Description:** Staff members and their profiles linked to users.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `user` | OneToOneField(User) | Nullable, CASCADE | NULL | Linked user account |
| `first_name` | CharField(100) | Nullable, Indexed | NULL | First name |
| `last_name` | CharField(100) | Nullable, Indexed | NULL | Last name |
| `email` | EmailField | Unique, Nullable, Indexed | NULL | Email address |
| `active` | BooleanField | Indexed, NOT NULL | True | Active status |

**Constraints:**
- Unique Constraint: `unique_staff_email` on `email` (where email IS NOT NULL)

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `email`
- Indexed: `first_name`, `last_name`, `email`, `active`, `user_id`

**Relationships:**
- One-to-One: `user` → `User` (CASCADE on delete)
- Reverse: `staff_profile` from User
- Reverse: `staffrole_set` from StaffRole
- Reverse: `owned_departments` from Department
- Reverse: `program_manager_assignments` from ProgramManagerAssignment
- Reverse: `service_manager_assignments` from ProgramServiceManagerAssignment
- Reverse: `department_leader_assignments` from DepartmentLeaderAssignment
- Reverse: `restrictions_entered` from ServiceRestriction
- Reverse: `restrictions_affecting` from ServiceRestriction
- Reverse: `client_uploads` from ClientUploadLog
- Reverse: `notifications` from Notification
- Reverse: `service_restriction_notification` from ServiceRestrictionNotificationSubscription

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Staff model with: `id`, `external_id`, `created_at`, `updated_at`, `first_name`, `last_name`, `email`, `active`, `user`
  - Added unique constraint: `unique_staff_email` on `email`

---

### staff_roles

**Table Name:** `staff_roles`  
**Model:** `core.StaffRole`  
**Description:** Many-to-many relationship between Staff and Roles.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `role` | ForeignKey(Role) | Indexed, NOT NULL | - | Role assigned |

**Constraints:**
- Unique Together: `('staff', 'role')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `role_id`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `role` → `Role` (CASCADE)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created StaffRole model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `role`
  - Added unique together constraint: `('staff', 'role')`

---

### programs

**Table Name:** `programs`  
**Model:** `core.Program`  
**Description:** Programs offered by departments.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `name` | CharField(255) | Indexed, NOT NULL | - | Program name |
| `department` | ForeignKey(Department) | Indexed, NOT NULL | - | Department |
| `location` | CharField(255) | Indexed, NOT NULL | - | Program location |
| `capacity_current` | PositiveIntegerField | NOT NULL | 100 | Current capacity |
| `no_capacity_limit` | BooleanField | NOT NULL | False | No capacity limit flag |
| `capacity_effective_date` | DateField | Nullable | NULL | Capacity effective date |
| `status` | CharField(20) | Indexed, NOT NULL | 'active' | Program status |
| `description` | TextField | Nullable | NULL | Program description |
| `created_by` | CharField(255) | Nullable | NULL | Creator name |
| `updated_by` | CharField(255) | Nullable | NULL | Last updater name |
| `is_archived` | BooleanField | Indexed, NOT NULL | False | Whether archived |
| `archived_at` | DateTimeField | Nullable, Indexed | NULL | Archive timestamp |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `name`, `department_id`, `location`, `status`, `is_archived`, `archived_at`

**Relationships:**
- Foreign Key: `department` → `Department` (CASCADE)
- Reverse: `subprograms` from SubProgram
- Reverse: `clientprogramenrollment_set` from ClientProgramEnrollment
- Reverse: `intake_set` from Intake
- Reverse: `discharge_set` from Discharge
- Reverse: `servicerestriction_set` from ServiceRestriction
- Reverse: `programstaff_set` from ProgramStaff
- Reverse: `manager_assignments` from ProgramManagerAssignment
- Reverse: `staff_assignments` from StaffProgramAssignment

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Program model with: `id`, `external_id`, `created_at`, `updated_at`, `name`, `department`, `location`, `capacity_current` (default=0), `capacity_effective_date`

- **0025_set_default_program_capacity.py**
  - Changed `capacity_current` default from 0 to 100

- **0030_add_subprogram_model.py**
  - Created SubProgram model (related model)

- **0060_add_audit_fields_to_program.py**
  - Added `created_by` (CharField, nullable)
  - Added `updated_by` (CharField, nullable)

- **0065_client_archived_at_client_is_archived_and_more.py** (2025-11-05)
  - Added `is_archived` (BooleanField, default=False, indexed)
  - Added `archived_at` (DateTimeField, nullable, indexed)

- **0072_program_no_capacity_limit.py**
  - Added `no_capacity_limit` (BooleanField, default=False)
  - Added `status` field (CharField, choices, default='active')
  - Added `description` field (TextField, nullable)

---

### subprograms

**Table Name:** `subprograms`  
**Model:** `core.SubProgram`  
**Description:** Sub-programs within main programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `name` | CharField(255) | Indexed, NOT NULL | - | Sub-program name |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Parent program |
| `description` | TextField | Nullable | NULL | Description |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |

**Constraints:**
- Unique Together: `('name', 'program')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `name`, `program_id`, `is_active`

**Relationships:**
- Foreign Key: `program` → `Program` (CASCADE)
- Reverse: `clientprogramenrollment_set` from ClientProgramEnrollment

#### Migration History

- **0030_add_subprogram_model.py**
  - Created SubProgram model with: `id`, `external_id`, `created_at`, `updated_at`, `name`, `program`, `description`, `is_active`
  - Added unique together constraint: `('name', 'program')`

---

### program_staff

**Table Name:** `program_staff`  
**Model:** `core.ProgramStaff`  
**Description:** Many-to-many relationship between Programs and Staff.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `is_manager` | BooleanField | Indexed, NOT NULL | False | Manager flag |

**Constraints:**
- Unique Together: `('program', 'staff')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `program_id`, `staff_id`, `is_manager`

**Relationships:**
- Foreign Key: `program` → `Program` (CASCADE)
- Foreign Key: `staff` → `Staff` (CASCADE)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created ProgramStaff model with: `id`, `external_id`, `created_at`, `updated_at`, `program`, `staff`, `is_manager`
  - Added unique together constraint: `('program', 'staff')`

---

### clients

**Table Name:** `clients`  
**Model:** `core.Client`  
**Description:** Client records with comprehensive personal, demographic, and program information.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client_id` | CharField(100) | Nullable, Indexed | NULL | External client ID |
| `last_name` | CharField(100) | Indexed, NOT NULL | - | Last name |
| `first_name` | CharField(100) | Indexed, NOT NULL | - | First name |
| `middle_name` | CharField(100) | Nullable, Indexed | NULL | Middle name |
| `preferred_name` | CharField(100) | Nullable, Indexed | NULL | Preferred name |
| `alias` | CharField(100) | Nullable, Indexed | NULL | Last name at birth |
| `dob` | DateField | Nullable, Indexed | NULL | Date of birth |
| `age` | IntegerField | Nullable | NULL | Calculated age |
| `gender` | CharField(50) | Nullable, Indexed | NULL | Gender |
| `gender_identity` | CharField(100) | Nullable, Indexed | NULL | Gender identity |
| `pronoun` | CharField(50) | Nullable, Indexed | NULL | Pronoun |
| `marital_status` | CharField(50) | Nullable, Indexed | NULL | Marital status |
| `citizenship_status` | CharField(100) | Nullable, Indexed | NULL | Citizenship status |
| `location_county` | CharField(100) | Nullable, Indexed | NULL | County |
| `province` | CharField(100) | Nullable, Indexed | NULL | Province |
| `city` | CharField(100) | Nullable, Indexed | NULL | City |
| `postal_code` | CharField(20) | Nullable, Indexed | NULL | Postal code |
| `address` | CharField(500) | Nullable | NULL | Address line 1 |
| `address_2` | CharField(255) | Nullable | NULL | Address line 2 |
| `language` | CharField(100) | Nullable, Indexed | NULL | Language |
| `preferred_language` | CharField(100) | Nullable, Indexed | NULL | Preferred language |
| `mother_tongue` | CharField(100) | Nullable, Indexed | NULL | Mother tongue |
| `official_language` | CharField(100) | Nullable, Indexed | NULL | Official language |
| `language_interpreter_required` | BooleanField | Indexed, NOT NULL | False | Interpreter required |
| `self_identification_race_ethnicity` | CharField(200) | Nullable, Indexed | NULL | Self-identified race/ethnicity |
| `ethnicity` | JSONField | NOT NULL | `[]` | List of ethnicities |
| `aboriginal_status` | CharField(100) | Nullable, Indexed | NULL | Aboriginal status |
| `lgbtq_status` | CharField(100) | Nullable, Indexed | NULL | LGBTQ+ status |
| `veteran_status` | CharField(100) | Nullable, Indexed | NULL | Veteran status |
| `legal_status` | CharField(100) | Nullable, Indexed | NULL | Legal status |
| `highest_level_education` | CharField(100) | Nullable, Indexed | NULL | Education level |
| `children_home` | BooleanField | Indexed, NOT NULL | False | Children at home |
| `children_number` | IntegerField | Nullable | NULL | Number of children |
| `lhin` | CharField(100) | Nullable, Indexed | NULL | Local Health Integration Network |
| `medical_conditions` | TextField | Nullable | NULL | Medical conditions |
| `primary_diagnosis` | CharField(255) | Nullable | NULL | Primary diagnosis |
| `family_doctor` | CharField(255) | Nullable | NULL | Family doctor |
| `health_card_number` | CharField(50) | Nullable, Indexed | NULL | Health card number |
| `health_card_version` | CharField(10) | Nullable | NULL | Health card version |
| `health_card_exp_date` | DateField | Nullable | NULL | Health card expiry |
| `health_card_issuing_province` | CharField(100) | Nullable | NULL | HC issuing province |
| `no_health_card_reason` | CharField(255) | Nullable | NULL | No HC reason |
| `permission_to_phone` | BooleanField | Indexed, NOT NULL | False | Phone permission |
| `permission_to_email` | BooleanField | Indexed, NOT NULL | False | Email permission |
| `preferred_communication_method` | CharField(50) | Nullable, Indexed | NULL | Preferred communication |
| `phone` | CharField(20) | Nullable, Indexed | NULL | Phone number |
| `phone_work` | CharField(20) | Nullable | NULL | Work phone |
| `phone_alt` | CharField(20) | Nullable | NULL | Alternative phone |
| `email` | EmailField | Nullable, Indexed | NULL | Email address |
| `next_of_kin` | JSONField | NOT NULL | `{}` | Next of kin info |
| `emergency_contact` | JSONField | NOT NULL | `{}` | Emergency contact info |
| `comments` | TextField | Nullable | NULL | Comments/notes |
| `program` | CharField(255) | Nullable, Indexed | NULL | Program name (legacy) |
| `sub_program` | CharField(255) | Nullable, Indexed | NULL | Sub-program name (legacy) |
| `support_workers` | JSONField | NOT NULL | `[]` | Support workers list |
| `level_of_support` | CharField(100) | Nullable, Indexed | NULL | Support level |
| `client_type` | CharField(100) | Nullable, Indexed | NULL | Client type |
| `admission_date` | DateField | Nullable, Indexed | NULL | Admission date |
| `discharge_date` | DateField | Nullable, Indexed | NULL | Discharge date |
| `days_elapsed` | IntegerField | Nullable | NULL | Days elapsed |
| `program_status` | CharField(100) | Nullable, Indexed | NULL | Program status |
| `reason_discharge` | CharField(255) | Nullable | NULL | Discharge reason |
| `receiving_services` | BooleanField | Indexed, NOT NULL | False | Receiving services |
| `receiving_services_date` | DateField | Nullable, Indexed | NULL | Services start date |
| `referral_source` | CharField(255) | Nullable, Indexed | NULL | Referral source |
| `chart_number` | CharField(100) | Nullable, Indexed | NULL | Chart number |
| `source` | CharField(50) | Nullable, Indexed | NULL | Source system (SMIS/EMHware/FFAI) |
| `legacy_client_ids` | JSONField | NOT NULL | `[]` | Legacy client IDs list |
| `secondary_source_id` | CharField(100) | Nullable, Indexed | NULL | Merged duplicate client ID |
| `is_archived` | BooleanField | Indexed, NOT NULL | False | Whether archived |
| `archived_at` | DateTimeField | Nullable, Indexed | NULL | Archive timestamp |
| `is_inactive` | BooleanField | Indexed, NOT NULL | False | Inactive status |
| `image` | URLField(500) | Nullable | NULL | Profile image URL (legacy) |
| `profile_picture` | ImageField | Nullable | NULL | Profile picture file |
| `contact_information` | JSONField | NOT NULL | `{}` | Contact info (legacy) |
| `addresses` | JSONField | NOT NULL | `[]` | Addresses list (legacy) |
| `uid_external` | CharField(255) | Unique, Nullable, Indexed | NULL | External UID |
| `languages_spoken` | JSONField | NOT NULL | `[]` | Languages spoken (legacy) |
| `indigenous_status` | CharField(100) | Nullable, Indexed | NULL | Indigenous status |
| `country_of_birth` | CharField(100) | Nullable, Indexed | NULL | Country of birth |
| `sexual_orientation` | CharField(100) | Nullable, Indexed | NULL | Sexual orientation |
| `created_by` | CharField(255) | Nullable | NULL | Creator name |
| `updated_by` | CharField(255) | Nullable | NULL | Last updater name |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `uid_external`
- Indexed: Multiple fields for performance (see model definition)

**Relationships:**
- Reverse: `extended` from ClientExtended
- Reverse: `clientprogramenrollment_set` from ClientProgramEnrollment
- Reverse: `intake_set` from Intake
- Reverse: `discharge_set` from Discharge
- Reverse: `servicerestriction_set` from ServiceRestriction
- Reverse: `primary_duplicates` from ClientDuplicate
- Reverse: `duplicate_of` from ClientDuplicate
- Reverse: `staff_assignments` from StaffClientAssignment

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Client model with basic fields: `id`, `external_id`, `created_at`, `updated_at`, `first_name`, `last_name`, `preferred_name`, `alias`, `dob`, `gender`, `sexual_orientation`, `languages_spoken`, `race`, `immigration_status`, `image`, `phone_number`, `email`, `address` (JSONField), `uid_external`
  - Added indexes: `first_name+last_name+dob`, `uid_external`, `email`, `phone_number`

- **0002_remove_client_address_client_addresses.py**
  - Removed `address` and `addresses` fields (later restored)

- **0005_migrate_contact_information.py**
  - Added `contact_information` JSONField

- **0008_alter_client_image.py**
  - Altered `image` field

- **0009_client_profile_picture.py**
  - Added `profile_picture` ImageField

- **0012_add_comprehensive_client_fields.py**
  - Added comprehensive client fields

- **0016_add_updated_by_to_client.py**
  - Added `updated_by` field

- **0022_alter_client_client_id_alter_client_image.py**
  - Added `client_id` field
  - Altered `image` field

- **0027_add_comprehensive_client_fields_v2.py**
  - Added more comprehensive fields

- **0028_remove_program_fields_from_client.py**
  - Removed program-related fields

- **0029_restore_program_fields.py**
  - Restored program fields

- **0032_add_receiving_services_date_to_client.py**
  - Added `receiving_services_date`

- **0033_remove_client_receiving_services_date.py**
  - Removed `receiving_services_date`

- **0045_add_client_source_field.py**
  - Added `source` field (SMIS/EMHware)

- **0050_add_receiving_services_date_to_client.py**
  - Re-added `receiving_services_date`

- **0051_clientextended.py**
  - Created ClientExtended model (related model)

- **0054_make_dob_nullable.py**
  - Made `dob` nullable

- **0055_fix_ethnicity_nullable.py**
  - Fixed ethnicity field nullability

- **0056_fix_all_nullable_fields.py**
  - Fixed multiple nullable fields

- **0057_add_created_by_to_client.py**
  - Added `created_by` field

- **0058_fix_referral_source_length.py**
  - Fixed `referral_source` max_length

- **0063_alter_client_gender.py**
  - Altered `gender` field

- **0065_client_archived_at_client_is_archived_and_more.py** (2025-11-05)
  - Added `is_archived` (BooleanField, default=False, indexed)
  - Added `archived_at` (DateTimeField, nullable, indexed)

- **0067_client_is_inactive.py**
  - Added `is_inactive` (BooleanField, default=False, indexed)

- **0074_add_veteran_legal_status_fields.py**
  - Added `veteran_status` field
  - Added `legal_status` field

- **0075_add_preferred_communication_method.py**
  - Added `preferred_communication_method` field

- **0077_add_legacy_client_ids_and_secondary_source_id.py**
  - Added `legacy_client_ids` JSONField
  - Added `secondary_source_id` CharField
  - Updated `source` choices to include 'FFAI'

---

### client_extended

**Table Name:** `client_extended`  
**Model:** `core.ClientExtended`  
**Description:** Extended client information with detailed demographics, health, accessibility, and housing information.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | OneToOneField(Client) | NOT NULL | - | Related client |
| `indigenous_identity` | CharField(200) | Nullable | NULL | Indigenous identity |
| `military_status` | CharField(200) | Nullable | NULL | Military status |
| `refugee_status` | CharField(200) | Nullable | NULL | Refugee status |
| `household_size` | IntegerField | Nullable | NULL | Household size |
| `family_head_client_no` | CharField(100) | Nullable | NULL | Family head client number |
| `relationship` | CharField(100) | Nullable | NULL | Relationship |
| `primary_worker` | CharField(200) | Nullable | NULL | Primary worker |
| `chronically_homeless` | BooleanField | NOT NULL | False | Chronically homeless |
| `num_bednights_current_stay` | IntegerField | Nullable | NULL | Bed nights current stay |
| `length_homeless_3yrs` | IntegerField | Nullable | NULL | Length homeless 3 years |
| `income_source` | CharField(200) | Nullable | NULL | Income source |
| `taxation_year_filed` | CharField(20) | Nullable | NULL | Taxation year filed |
| `status_id` | CharField(200) | Nullable | NULL | Status ID |
| `picture_id` | CharField(200) | Nullable | NULL | Picture ID |
| `other_id` | CharField(200) | Nullable | NULL | Other ID |
| `bnl_consent` | BooleanField | NOT NULL | False | BNL consent |
| `allergies` | TextField | Nullable | NULL | Allergies |
| `harm_reduction_support` | BooleanField | NOT NULL | False | Harm reduction support |
| `medication_support` | BooleanField | NOT NULL | False | Medication support |
| `pregnancy_support` | BooleanField | NOT NULL | False | Pregnancy support |
| `mental_health_support` | BooleanField | NOT NULL | False | Mental health support |
| `physical_health_support` | BooleanField | NOT NULL | False | Physical health support |
| `daily_activities_support` | BooleanField | NOT NULL | False | Daily activities support |
| `other_health_supports` | TextField | Nullable | NULL | Other health supports |
| `cannot_use_stairs` | BooleanField | NOT NULL | False | Cannot use stairs |
| `limited_mobility` | BooleanField | NOT NULL | False | Limited mobility |
| `wheelchair_accessibility` | BooleanField | NOT NULL | False | Wheelchair accessibility |
| `vision_hearing_speech_supports` | TextField | Nullable | NULL | Vision/hearing/speech supports |
| `english_translator` | BooleanField | NOT NULL | False | English translator |
| `reading_supports` | BooleanField | NOT NULL | False | Reading supports |
| `other_accessibility_supports` | TextField | Nullable | NULL | Other accessibility supports |
| `pet_owner` | BooleanField | NOT NULL | False | Pet owner |
| `legal_support` | BooleanField | NOT NULL | False | Legal support |
| `immigration_support` | BooleanField | NOT NULL | False | Immigration support |
| `religious_cultural_supports` | TextField | Nullable | NULL | Religious/cultural supports |
| `safety_concerns` | TextField | Nullable | NULL | Safety concerns |
| `intimate_partner_violence_support` | BooleanField | NOT NULL | False | IPV support |
| `human_trafficking_support` | BooleanField | NOT NULL | False | Human trafficking support |
| `other_supports` | TextField | Nullable | NULL | Other supports |
| `access_to_housing_application` | CharField(255) | Nullable | NULL | Access to housing application |
| `access_to_housing_no` | CharField(100) | Nullable | NULL | Access to housing number |
| `access_point_application` | CharField(255) | Nullable | NULL | Access point application |
| `access_point_no` | CharField(100) | Nullable | NULL | Access point number |
| `cars` | CharField(255) | Nullable | NULL | Cars |
| `cars_no` | CharField(100) | Nullable | NULL | Cars number |
| `discharge_disposition` | CharField(255) | Nullable | NULL | Discharge disposition |
| `intake_status` | CharField(100) | Nullable | NULL | Intake status |
| `lived_last_12_months` | TextField | Nullable | NULL | Lived last 12 months |
| `reason_for_service` | TextField | Nullable | NULL | Reason for service |
| `intake_date` | DateField | Nullable | NULL | Intake date |
| `service_end_date` | DateField | Nullable | NULL | Service end date |
| `rejection_date` | DateField | Nullable | NULL | Rejection date |
| `rejection_reason` | TextField | Nullable | NULL | Rejection reason |
| `room` | CharField(50) | Nullable | NULL | Room |
| `bed` | CharField(50) | Nullable | NULL | Bed |
| `occupancy_status` | CharField(100) | Nullable | NULL | Occupancy status |
| `bed_nights_historical` | IntegerField | Nullable | NULL | Bed nights historical |
| `restriction_reason` | TextField | Nullable | NULL | Restriction reason |
| `restriction_date` | DateField | Nullable | NULL | Restriction date |
| `restriction_duration_days` | IntegerField | Nullable | NULL | Restriction duration days |
| `restriction_status` | CharField(100) | Nullable | NULL | Restriction status |
| `early_termination_by` | CharField(255) | Nullable | NULL | Early termination by |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `client_id` (OneToOne)

**Relationships:**
- One-to-One: `client` → `Client` (CASCADE)

#### Migration History

- **0051_clientextended.py**
  - Created ClientExtended model with comprehensive extended fields

- **0052_clientextended_access_point_application_and_more.py**
  - Added access point and housing application fields
  - Added intake/discharge/housing fields

- **0053_clientextended_relationship.py**
  - Added relationship field

---

### client_program_enrollments

**Table Name:** `client_program_enrollments`  
**Model:** `core.ClientProgramEnrollment`  
**Description:** Tracks client enrollments in programs with status and dates.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client enrolled |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `sub_program` | ForeignKey(SubProgram) | Nullable, Indexed | NULL | Sub-program |
| `start_date` | DateField | Indexed, NOT NULL | - | Enrollment start date |
| `end_date` | DateField | Nullable, Indexed | NULL | Enrollment end date |
| `status` | CharField(20) | Indexed, NOT NULL | 'pending' | Enrollment status |
| `notes` | TextField | Nullable | NULL | Notes |
| `days_elapsed` | IntegerField | Nullable | NULL | Days elapsed |
| `receiving_services_date` | DateField | Nullable, Indexed | NULL | Services start date |
| `created_by` | CharField(255) | Nullable | NULL | Creator name |
| `updated_by` | CharField(255) | Nullable | NULL | Last updater name |
| `is_archived` | BooleanField | Indexed, NOT NULL | False | Whether archived |
| `archived_at` | DateTimeField | Nullable, Indexed | NULL | Archive timestamp |

**Constraints:**
- Check Constraint: `end_date_after_start_date` (end_date >= start_date)

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `client_id`, `program_id`, `sub_program_id`, `start_date`, `end_date`, `status`, `receiving_services_date`, `is_archived`, `archived_at`

**Relationships:**
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `program` → `Program` (CASCADE)
- Foreign Key: `sub_program` → `SubProgram` (CASCADE, nullable)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created ClientProgramEnrollment model with: `id`, `external_id`, `created_at`, `updated_at`, `start_date`, `end_date`
  - Added foreign keys: `client`, `program`
  - Added constraint: `end_date_after_start_date`

- **0003_remove_intake_source_system_and_more.py**
  - Added `notes` field (TextField, nullable)
  - Added `status` field (CharField, choices, default='pending')

- **0020_add_created_by_to_enrollment.py**
  - Added `created_by` field (CharField, nullable)

- **0017_add_updated_by_to_enrollment.py**
  - Added `updated_by` field (CharField, nullable)

- **0023_add_archived_to_enrollment.py**
  - Added `is_archived` field (BooleanField, default=False, indexed)
  - Updated `status` choices to include 'archived'

- **0030_add_subprogram_model.py**
  - Added `sub_program` ForeignKey (nullable)

- **0031_add_enrollment_details_fields.py**
  - Added `days_elapsed` field (IntegerField, nullable)
  - Added `receiving_services_date` field (DateField, nullable, indexed)

- **0065_client_archived_at_client_is_archived_and_more.py** (2025-11-05)
  - Added `archived_at` field (DateTimeField, nullable, indexed)

---

### intakes

**Table Name:** `intakes`  
**Model:** `core.Intake`  
**Description:** Tracks client intake records into programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `department` | ForeignKey(Department) | Nullable, Indexed | NULL | Department |
| `intake_date` | DateField | Indexed, NOT NULL | - | Intake date |
| `intake_database` | CharField(100) | Indexed, NOT NULL | 'CCD' | Intake database |
| `referral_source` | CharField(255) | Nullable, Indexed | NULL | Referral source |
| `intake_housing_status` | CharField(20) | Indexed, NOT NULL | 'unknown' | Housing status |
| `notes` | TextField | Nullable | NULL | Notes |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `client_id`, `program_id`, `department_id`, `intake_date`, `intake_database`, `referral_source`, `intake_housing_status`
- Composite: `intake_date_idx`, `intake_source_idx`, `intake_housing_idx`

**Relationships:**
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `program` → `Program` (CASCADE)
- Foreign Key: `department` → `Department` (CASCADE, nullable)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Intake model with: `id`, `external_id`, `created_at`, `updated_at`, `intake_date`, `source_system`, `client`, `program`

- **0003_remove_intake_source_system_and_more.py**
  - **Removed `source_system` field**
  - Added `department` ForeignKey (nullable)
  - Added `intake_database` CharField (default='CCD', indexed)
  - Added `intake_housing_status` CharField (choices, default='unknown', indexed)
  - Added `notes` TextField (nullable)
  - Added `referral_source` CharField (choices, default='SMIS', indexed)
  - Added indexes: `intake_date_idx`, `intake_source_idx`, `intake_housing_idx`

---

### discharges

**Table Name:** `discharges`  
**Model:** `core.Discharge`  
**Description:** Tracks client discharges from programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `discharge_date` | DateField | Indexed, NOT NULL | - | Discharge date |
| `reason` | TextField | NOT NULL | - | Discharge reason |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `client_id`, `program_id`, `discharge_date`

**Relationships:**
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `program` → `Program` (CASCADE)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created Discharge model with: `id`, `external_id`, `created_at`, `updated_at`, `discharge_date`, `reason`, `client`, `program`

---

### service_restrictions

**Table Name:** `service_restrictions`  
**Model:** `core.ServiceRestriction`  
**Description:** Service restrictions preventing client enrollment in programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client |
| `scope` | CharField(10) | Indexed, NOT NULL | - | Restriction scope (org/program) |
| `program` | ForeignKey(Program) | Nullable, Indexed | NULL | Program (if scope='program') |
| `restriction_type` | JSONField | NOT NULL | `[]` | Restriction type list |
| `is_bill_168` | BooleanField | Indexed, NOT NULL | False | Bill 168 flag |
| `is_no_trespass` | BooleanField | Indexed, NOT NULL | False | No trespass flag |
| `start_date` | DateField | Indexed, NOT NULL | - | Restriction start date |
| `end_date` | DateField | Nullable, Indexed | NULL | Restriction end date |
| `is_indefinite` | BooleanField | Indexed, NOT NULL | False | Indefinite restriction |
| `is_archived` | BooleanField | Indexed, NOT NULL | False | Whether archived |
| `archived_at` | DateTimeField | Nullable, Indexed | NULL | Archive timestamp |
| `behaviors` | JSONField | NOT NULL | `[]` | Behaviors list |
| `notes` | TextField | Nullable | NULL | Notes |
| `entered_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Staff who entered |
| `affected_staff` | ForeignKey(Staff) | Nullable, Indexed | NULL | Affected staff |
| `created_by` | CharField(255) | Nullable | NULL | Creator name |
| `updated_by` | CharField(255) | Nullable | NULL | Last updater name |

**Constraints:**
- Check Constraint: `valid_scope_program_combination` (if scope='program', program must not be null; if scope='org', program must be null)
- Check Constraint: `indefinite_restriction_no_end_date` (if is_indefinite=True, end_date must be null)

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `client_id`, `scope`, `program_id`, `start_date`, `end_date`, `is_indefinite`, `is_bill_168`, `is_no_trespass`, `is_archived`, `archived_at`, `entered_by_id`, `affected_staff_id`

**Relationships:**
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `program` → `Program` (CASCADE, nullable)
- Foreign Key: `entered_by` → `Staff` (SET_NULL, nullable)
- Foreign Key: `affected_staff` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created ServiceRestriction model with: `id`, `external_id`, `created_at`, `updated_at`, `scope`, `start_date`, `end_date`, `reason` (TextField), `client`, `program`
  - Added constraint: `valid_scope_program_combination`

- **0013_add_restriction_enhancements.py**
  - **Removed `reason` field**
  - Added `behaviors` JSONField (default=list)
  - Added `is_indefinite` BooleanField (default=False, indexed)
  - Added `notes` TextField (nullable)
  - Added `restriction_type` CharField (choices, default='general')
  - Added constraint: `indefinite_restriction_no_end_date`

- **0014_add_behavioral_restrictions_and_images.py**
  - Updated restriction_type choices

- **0018_add_updated_by_to_restriction.py**
  - Added `updated_by` field (CharField, nullable)

- **0019_add_created_by_to_restriction.py**
  - Added `created_by` field (CharField, nullable)

- **0026_add_archived_to_restrictions.py**
  - Added `is_archived` field (BooleanField, default=False)

- **0034_add_bill_168_no_trespass_fields.py**
  - Added `is_bill_168` BooleanField (default=False, indexed)
  - Added `is_no_trespass` BooleanField (default=False, indexed)
  - Altered `restriction_type` choices

- **0036_convert_restriction_type_to_json.py** through **0040_convert_restriction_type_to_jsonfield.py**
  - Converted `restriction_type` from CharField to JSONField through multiple migrations

- **0065_client_archived_at_client_is_archived_and_more.py** (2025-11-05)
  - Added `archived_at` field (DateTimeField, nullable, indexed)

- **0068_add_entered_by_to_service_restriction.py**
  - Added `entered_by` ForeignKey(Staff, nullable)

- **0069_remove_servicerestriction_valid_scope_program_combination_and_more.py**
  - Removed and re-added `valid_scope_program_combination` constraint

- **0076_add_affected_staff_to_service_restriction.py**
  - Added `affected_staff` ForeignKey(Staff, nullable, indexed)

---

### audit_logs

**Table Name:** `audit_logs`  
**Model:** `core.AuditLog`  
**Description:** Audit trail for all entity changes in the system.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `entity` | CharField(100) | Indexed, NOT NULL | - | Entity name |
| `entity_id` | UUIDField | Indexed, NOT NULL | - | Entity UUID |
| `action` | CharField(20) | Indexed, NOT NULL | - | Action type |
| `changed_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Staff who made change |
| `changed_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Change timestamp |
| `diff_json` | JSONField | NOT NULL | - | Change diff JSON |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `entity`, `entity_id`, `action`, `changed_by_id`, `changed_at`

**Relationships:**
- Foreign Key: `changed_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created AuditLog model with: `id`, `external_id`, `created_at`, `updated_at`, `entity`, `entity_id`, `action`, `changed_at`, `diff_json`
  - Added `changed_by` ForeignKey(Staff, nullable)

- **0041_add_login_logout_actions.py**
  - Updated `action` choices to include 'login', 'logout'

- **0066_add_restore_action_to_audit_log.py**
  - Updated `action` choices to include 'restore', 'archive'

---

### client_duplicates

**Table Name:** `client_duplicates`  
**Model:** `core.ClientDuplicate`  
**Description:** Tracks potential duplicate clients for manual review and merging.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `primary_client` | ForeignKey(Client) | Indexed, NOT NULL | - | Primary client |
| `duplicate_client` | ForeignKey(Client) | Indexed, NOT NULL | - | Duplicate client |
| `similarity_score` | FloatField | Indexed, NOT NULL | - | Similarity score (0-1) |
| `match_type` | CharField(50) | Indexed, NOT NULL | - | Match type |
| `confidence_level` | CharField(20) | Indexed, NOT NULL | - | Confidence level |
| `status` | CharField(30) | Indexed, NOT NULL | 'pending' | Review status |
| `match_details` | JSONField | NOT NULL | `{}` | Match details |
| `reviewed_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Reviewer |
| `reviewed_at` | DateTimeField | Nullable, Indexed | NULL | Review timestamp |
| `review_notes` | TextField | Nullable | NULL | Review notes |
| `detection_source` | CharField(50) | Nullable, Indexed | NULL | Detection source |

**Constraints:**
- Unique Together: `('primary_client', 'duplicate_client')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `primary_client_id`, `duplicate_client_id`, `similarity_score`, `match_type`, `confidence_level`, `status`, `reviewed_by_id`, `reviewed_at`, `detection_source`
- Composite: `status+confidence_level`, `similarity_score`, `match_type`

**Relationships:**
- Foreign Key: `primary_client` → `Client` (CASCADE)
- Foreign Key: `duplicate_client` → `Client` (CASCADE)
- Foreign Key: `reviewed_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0006_clientduplicate.py** (2025-09-22)
  - Created ClientDuplicate model with: `id`, `external_id`, `created_at`, `updated_at`, `primary_client`, `duplicate_client`, `similarity_score`, `match_type`, `confidence_level`, `status`, `match_details`, `reviewed_by`, `reviewed_at`, `review_notes`
  - Added unique together constraint: `('primary_client', 'duplicate_client')`
  - Added indexes: `status+confidence_level`, `similarity_score`, `match_type`

- **0078_add_detection_source_to_client_duplicate.py**
  - Added `detection_source` CharField (nullable, indexed)

---

### program_manager_assignments

**Table Name:** `program_manager_assignments`  
**Model:** `core.ProgramManagerAssignment`  
**Description:** Assigns Manager role staff to specific programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `assigned_by` | ForeignKey(Staff) | Nullable | NULL | Assigner |
| `assigned_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Assignment timestamp |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `notes` | TextField | Nullable | NULL | Notes |

**Constraints:**
- Unique Together: `('staff', 'program')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `program_id`, `assigned_at`, `is_active`
- Composite: `staff+is_active`, `program+is_active`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `program` → `Program` (CASCADE)
- Foreign Key: `assigned_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0011_programmanagerassignment.py** (2025-09-30)
  - Created ProgramManagerAssignment model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `program`, `assigned_by`, `assigned_at`, `is_active`, `notes`
  - Added unique together constraint: `('staff', 'program')`
  - Added indexes: `staff+is_active`, `program+is_active`

---

### program_service_manager_assignments

**Table Name:** `program_service_manager_assignments`  
**Model:** `core.ProgramServiceManagerAssignment`  
**Description:** Assigns Manager role staff to specific program services.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `program_service` | ForeignKey(ProgramService) | Indexed, NOT NULL | - | Program service |
| `assigned_by` | ForeignKey(Staff) | Nullable | NULL | Assigner |
| `assigned_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Assignment timestamp |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `notes` | TextField | Nullable | NULL | Notes |

**Constraints:**
- Unique Together: `('staff', 'program_service')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `program_service_id`, `assigned_at`, `is_active`
- Composite: `staff+is_active`, `program_service+is_active`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `program_service` → `ProgramService` (CASCADE)
- Foreign Key: `assigned_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0010_programservicemanagerassignment.py** (2025-09-30)
  - Created ProgramServiceManagerAssignment model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `program_service`, `assigned_by`, `assigned_at`, `is_active`, `notes`
  - Added unique together constraint: `('staff', 'program_service')`
  - Added indexes: `staff+is_active`, `program_service+is_active`

---

### department_leader_assignments

**Table Name:** `department_leader_assignments`  
**Model:** `core.DepartmentLeaderAssignment`  
**Description:** Assigns Leader role staff to specific departments.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `department` | ForeignKey(Department) | Indexed, NOT NULL | - | Department |
| `assigned_by` | ForeignKey(Staff) | Nullable | NULL | Assigner |
| `assigned_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Assignment timestamp |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `notes` | TextField | Nullable | NULL | Notes |

**Constraints:**
- Unique Together: `('staff', 'department')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `department_id`, `assigned_at`, `is_active`
- Composite: `staff+is_active`, `department+is_active`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `department` → `Department` (CASCADE)
- Foreign Key: `assigned_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0044_add_department_leader_assignment.py** (2025-10-14)
  - Created DepartmentLeaderAssignment model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `department`, `assigned_by`, `assigned_at`, `is_active`, `notes`
  - Added unique together constraint: `('staff', 'department')`
  - Added indexes: `staff+is_active`, `department+is_active`

---

### email_recipients

**Table Name:** `email_recipients`  
**Model:** `core.EmailRecipient`  
**Description:** Email addresses that receive daily client reports.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `email` | EmailField | Unique, Indexed, NOT NULL | - | Email address |
| `name` | CharField(255) | NOT NULL | - | Recipient name |
| `frequency` | CharField(20) | NOT NULL | 'daily' | Report frequency |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `department` | ForeignKey(Department) | Nullable | NULL | Department filter |
| `notes` | TextField | Nullable | NULL | Notes |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `email`
- Indexed: `email`, `is_active`, `department_id`
- Composite: `email+is_active`, `department+is_active`

**Relationships:**
- Foreign Key: `department` → `Department` (SET_NULL, nullable)

#### Migration History

- **0046_emailrecipient.py** (2025-10-16)
  - Created EmailRecipient model with: `id`, `external_id`, `created_at`, `updated_at`, `email`, `name`, `is_active`, `department`, `notes`

- **0047_add_frequency_to_email_recipient.py**
  - Added `frequency` CharField (choices, default='daily')

- **0049_alter_emailrecipient_options.py**
  - Updated model options

---

### service_restriction_notification_subscriptions

**Table Name:** `service_restriction_notification_subscriptions`  
**Model:** `core.ServiceRestrictionNotificationSubscription`  
**Description:** Per-staff notification preferences for service restriction alerts.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | OneToOneField(Staff) | NOT NULL | - | Staff member |
| `email` | EmailField | Nullable | NULL | Destination email |
| `notify_new` | BooleanField | NOT NULL | True | Notify on new restrictions |
| `notify_expiring` | BooleanField | NOT NULL | True | Notify on expiring restrictions |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `staff_id` (OneToOne)

**Relationships:**
- One-to-One: `staff` → `Staff` (CASCADE)

#### Migration History

- **0070_servicerestrictionnotificationsubscription.py**
  - Created ServiceRestrictionNotificationSubscription model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `email`, `notify_new`, `notify_expiring`

---

### notifications

**Table Name:** `notifications`  
**Model:** `core.Notification`  
**Description:** Generic notifications for staff users with read/unread tracking.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `category` | CharField(100) | Indexed, NOT NULL | 'service_restriction' | Notification category |
| `title` | CharField(255) | NOT NULL | - | Notification title |
| `message` | TextField | NOT NULL | - | Notification message |
| `metadata` | JSONField | NOT NULL | `{}` | Additional metadata |
| `is_read` | BooleanField | Indexed, NOT NULL | False | Read status |
| `read_at` | DateTimeField | Nullable | NULL | Read timestamp |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `category`, `is_read`, `created_at`
- Composite: `staff+is_read+created_at`, `category+created_at`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)

#### Migration History

- **0071_notification.py**
  - Created Notification model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `category`, `title`, `message`, `metadata`, `is_read`, `read_at`
  - Added indexes: `staff+is_read+created_at`, `category+created_at`
  - Set ordering: `['-created_at']`

- **0073_rename_notifications_staff_i_c13930_idx_notificatio_staff_i_fd6636_idx_and_more.py**
  - Renamed indexes

---

### email_logs

**Table Name:** `email_logs`  
**Model:** `core.EmailLog`  
**Description:** Tracks sent emails for audit and debugging purposes.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `email_type` | CharField(20) | Indexed, NOT NULL | 'daily_report' | Email type |
| `subject` | CharField(255) | NOT NULL | - | Email subject |
| `recipient_email` | EmailField | NOT NULL | - | Recipient email |
| `recipient_name` | CharField(255) | Nullable | NULL | Recipient name |
| `email_body` | TextField | NOT NULL | - | HTML email body |
| `csv_attachment` | TextField | Nullable | NULL | CSV attachment data |
| `csv_filename` | CharField(255) | Nullable | NULL | CSV filename |
| `status` | CharField(20) | Indexed, NOT NULL | 'sent' | Send status |
| `sent_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Send timestamp |
| `error_message` | TextField | Nullable | NULL | Error message |
| `client_count` | PositiveIntegerField | NOT NULL | 0 | Client count |
| `report_date` | DateField | Indexed, NOT NULL | - | Report date |
| `frequency` | CharField(20) | NOT NULL | 'daily' | Report frequency |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `email_type`, `status`, `sent_at`, `report_date`
- Composite: `recipient_email+sent_at`, `email_type+status`, `report_date`, `sent_at`

**Relationships:**
- None (standalone table)

#### Migration History

- **0048_emaillog.py** (2025-10-16)
  - Created EmailLog model with: `id`, `external_id`, `created_at`, `updated_at`, `email_type`, `subject`, `recipient_email`, `recipient_name`, `email_body`, `csv_attachment`, `csv_filename`, `status`, `sent_at`, `error_message`, `client_count`, `report_date`, `frequency`
  - Added indexes: `recipient_email+sent_at`, `email_type+status`, `report_date`, `sent_at`
  - Set ordering: `['-sent_at']`

---

### client_upload_logs

**Table Name:** `client_upload_logs`  
**Model:** `core.ClientUploadLog`  
**Description:** Tracks client upload operations for performance monitoring and debugging.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `file_name` | CharField(255) | Indexed, NOT NULL | - | Uploaded file name |
| `file_size` | BigIntegerField | NOT NULL | - | File size in bytes |
| `file_type` | CharField(10) | Indexed, NOT NULL | - | File type (csv/xlsx/xls) |
| `source` | CharField(50) | Indexed, NOT NULL | - | Source system (SMIS/EMHware) |
| `total_rows` | IntegerField | NOT NULL | 0 | Total rows in file |
| `records_created` | IntegerField | NOT NULL | 0 | Records created |
| `records_updated` | IntegerField | NOT NULL | 0 | Records updated |
| `records_skipped` | IntegerField | NOT NULL | 0 | Records skipped |
| `duplicates_flagged` | IntegerField | NOT NULL | 0 | Duplicates flagged |
| `errors_count` | IntegerField | NOT NULL | 0 | Error count |
| `started_at` | DateTimeField | Indexed, NOT NULL | - | Upload start time |
| `completed_at` | DateTimeField | Nullable, Indexed | NULL | Upload completion time |
| `duration_seconds` | FloatField | Nullable | NULL | Upload duration |
| `status` | CharField(20) | Indexed, NOT NULL | 'success' | Upload status |
| `error_message` | TextField | Nullable | NULL | Error message |
| `error_details` | JSONField | NOT NULL | `[]` | Error details list |
| `upload_details` | JSONField | NOT NULL | `{}` | Upload metadata |
| `uploaded_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Uploader |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `file_name`, `file_type`, `source`, `started_at`, `completed_at`, `status`, `uploaded_by_id`
- Composite: `status+started_at`, `uploaded_by+started_at`, `source+started_at`

**Relationships:**
- Foreign Key: `uploaded_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0064_add_client_upload_log.py** (2025-11-03)
  - Created ClientUploadLog model with: `id`, `external_id`, `created_at`, `updated_at`, `file_name`, `file_size`, `file_type`, `source`, `total_rows`, `records_created`, `records_updated`, `records_skipped`, `duplicates_flagged`, `errors_count`, `started_at`, `completed_at`, `duration_seconds`, `status`, `error_message`, `error_details`, `upload_details`, `uploaded_by`
  - Added indexes: `status+started_at`, `uploaded_by+started_at`, `source+started_at`
  - Set ordering: `['-started_at']`

---

### pending_changes

**Table Name:** `pending_changes`  
**Model:** `core.PendingChange`  
**Description:** Tracks pending changes requiring approval (if used).

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `entity` | CharField(100) | Indexed, NOT NULL | - | Entity name |
| `entity_id` | UUIDField | Indexed, NOT NULL | - | Entity UUID |
| `diff_json` | JSONField | NOT NULL | - | Change diff JSON |
| `status` | CharField(20) | Indexed, NOT NULL | 'pending' | Approval status |
| `reviewed_at` | DateTimeField | Nullable, Indexed | NULL | Review timestamp |
| `rationale` | TextField | Nullable | NULL | Review rationale |
| `requested_by` | ForeignKey(Staff) | NOT NULL | - | Requester |
| `reviewed_by` | ForeignKey(Staff) | Nullable | NULL | Reviewer |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `entity`, `entity_id`, `status`, `reviewed_at`, `requested_by_id`, `reviewed_by_id`

**Relationships:**
- Foreign Key: `requested_by` → `Staff` (CASCADE)
- Foreign Key: `reviewed_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **0001_initial.py** (2025-09-04)
  - Created PendingChange model with: `id`, `external_id`, `created_at`, `updated_at`, `entity`, `entity_id`, `diff_json`, `status`, `reviewed_at`, `rationale`, `requested_by`, `reviewed_by`

---

## Clients App Tables

### client_notes

**Table Name:** `client_notes`  
**Model:** `clients.ClientNote`  
**Description:** Notes and comments related to clients.  
**Status:** Currently removed from database (models defined but migration 0004 deleted the table)

#### Final Schema (Model Definition)

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client |
| `title` | CharField(255) | NOT NULL | - | Note title |
| `content` | TextField | NOT NULL | - | Note content |
| `is_private` | BooleanField | Indexed, NOT NULL | False | Private flag |
| `created_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Creator |
| `updated_by` | CharField(255) | Nullable | NULL | Last updater name |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `client_id`, `is_private`, `created_by_id`, `created_at`
- Composite: `client+created_at`, `is_private`

**Relationships:**
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `created_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **clients/0001_initial.py** (2025-09-12)
  - Created ClientNote model with: `id`, `external_id`, `created_at`, `updated_at`, `title`, `content`, `is_private`, `client`
  - Added indexes: `client+created_at`, `is_private`

- **clients/0004_remove_clientdocument_client_and_more.py** (2025-10-17)
  - **DELETED ClientNote model** (table removed from database)
  - Note: Model definition exists in `clients/models.py` but table does not exist

---

### client_contacts

**Table Name:** `client_contacts`  
**Model:** `clients.ClientContact`  
**Description:** Contact information for clients (emergency contacts, family, etc.).  
**Status:** Currently removed from database (models defined but migration 0004 deleted the table)

#### Final Schema (Model Definition)

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client |
| `name` | CharField(255) | NOT NULL | - | Contact name |
| `relationship` | CharField(100) | NOT NULL | - | Relationship |
| `contact_type` | CharField(20) | Indexed, NOT NULL | - | Contact type |
| `phone_number` | CharField(20) | Nullable | NULL | Phone number |
| `email` | EmailField | Nullable | NULL | Email address |
| `address` | JSONField | NOT NULL | `{}` | Address JSON |
| `is_primary` | BooleanField | Indexed, NOT NULL | False | Primary contact flag |
| `notes` | TextField | Nullable | NULL | Notes |
| `created_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Creator |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `client_id`, `contact_type`, `is_primary`
- Composite: `client+contact_type`, `is_primary`

**Relationships:**
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `created_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **clients/0001_initial.py** (2025-09-12)
  - Created ClientContact model with: `id`, `external_id`, `created_at`, `updated_at`, `name`, `relationship`, `contact_type`, `phone_number`, `email`, `address`, `is_primary`, `client`
  - Added indexes: `client+contact_type`, `is_primary`

- **clients/0004_remove_clientdocument_client_and_more.py** (2025-10-17)
  - **DELETED ClientContact model** (table removed from database)
  - Note: Model definition exists in `clients/models.py` but table does not exist

---

## Programs App Tables

### program_capacities

**Table Name:** `program_capacities`  
**Model:** `programs.ProgramCapacity`  
**Description:** Historical capacity records for programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `effective_date` | DateField | Indexed, NOT NULL | - | Effective date |
| `capacity` | PositiveIntegerField | NOT NULL | - | Capacity value |
| `notes` | TextField | Nullable | NULL | Notes |

**Constraints:**
- Unique Together: `('program', 'effective_date')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `program_id`, `effective_date`
- Composite: `program+effective_date`

**Relationships:**
- Foreign Key: `program` → `Program` (CASCADE)

#### Migration History

- **programs/0001_initial.py**
  - Created ProgramCapacity model with: `id`, `external_id`, `created_at`, `updated_at`, `program`, `effective_date`, `capacity`, `notes`
  - Added unique together constraint: `('program', 'effective_date')`
  - Added index: `program+effective_date`

---

### program_locations

**Table Name:** `program_locations`  
**Model:** `programs.ProgramLocation`  
**Description:** Multiple locations for programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `name` | CharField(255) | NOT NULL | - | Location name |
| `address` | JSONField | NOT NULL | `{}` | Address JSON |
| `is_primary` | BooleanField | Indexed, NOT NULL | False | Primary location flag |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `program_id`, `is_primary`
- Composite: `program+is_primary`

**Relationships:**
- Foreign Key: `program` → `Program` (CASCADE)

#### Migration History

- **programs/0001_initial.py**
  - Created ProgramLocation model with: `id`, `external_id`, `created_at`, `updated_at`, `program`, `name`, `address`, `is_primary`
  - Added index: `program+is_primary`

---

### program_services

**Table Name:** `program_services`  
**Model:** `programs.ProgramService`  
**Description:** Services offered within programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `name` | CharField(255) | NOT NULL | - | Service name |
| `description` | TextField | NOT NULL | - | Service description |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `program_id`, `is_active`
- Composite: `program+is_active`

**Relationships:**
- Foreign Key: `program` → `Program` (CASCADE)
- Reverse: `manager_assignments` from ProgramServiceManagerAssignment

#### Migration History

- **programs/0001_initial.py**
  - Created ProgramService model with: `id`, `external_id`, `created_at`, `updated_at`, `program`, `name`, `description`, `is_active`
  - Added index: `program+is_active`

---

## Staff App Tables

### staff_schedules

**Table Name:** `staff_schedules`  
**Model:** `staff.StaffSchedule`  
**Description:** Staff work schedules by day of week.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `day_of_week` | PositiveSmallIntegerField | Indexed, NOT NULL | - | Day (0=Monday, 6=Sunday) |
| `start_time` | TimeField | NOT NULL | - | Start time |
| `end_time` | TimeField | NOT NULL | - | End time |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `day_of_week`, `is_active`
- Composite: `staff+day_of_week`, `is_active`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)

#### Migration History

- **staff/0001_initial.py**
  - Created StaffSchedule model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `day_of_week`, `start_time`, `end_time`, `is_active`
  - Added indexes: `staff+day_of_week`, `is_active`

---

### staff_notes

**Table Name:** `staff_notes`  
**Model:** `staff.StaffNote`  
**Description:** Notes related to staff members.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `title` | CharField(255) | NOT NULL | - | Note title |
| `content` | TextField | NOT NULL | - | Note content |
| `is_private` | BooleanField | Indexed, NOT NULL | False | Private flag |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `is_private`, `created_at`
- Composite: `staff+created_at`, `is_private`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)

#### Migration History

- **staff/0001_initial.py**
  - Created StaffNote model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `title`, `content`, `is_private`
  - Added indexes: `staff+created_at`, `is_private`

---

### staff_permissions

**Table Name:** `staff_permissions`  
**Model:** `staff.StaffPermission`  
**Description:** Custom permissions for staff members.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `permission_name` | CharField(255) | Indexed, NOT NULL | - | Permission name |
| `is_granted` | BooleanField | Indexed, NOT NULL | True | Granted status |
| `granted_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Granter |
| `granted_at` | DateTimeField | NOT NULL | `auto_now_add` | Grant timestamp |
| `expires_at` | DateTimeField | Nullable, Indexed | NULL | Expiration date |

**Constraints:**
- Unique Together: `('staff', 'permission_name')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `permission_name`, `is_granted`, `granted_by_id`, `expires_at`
- Composite: `staff+permission_name`, `is_granted`, `expires_at`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `granted_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **staff/0001_initial.py**
  - Created StaffPermission model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `permission_name`, `is_granted`, `granted_by`, `granted_at`, `expires_at`
  - Added unique together constraint: `('staff', 'permission_name')`
  - Added indexes: `staff+permission_name`, `is_granted`, `expires_at`

---

### staff_client_assignments

**Table Name:** `staff_client_assignments`  
**Model:** `staff.StaffClientAssignment`  
**Description:** Assigns staff members to specific clients.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `client` | ForeignKey(Client) | Indexed, NOT NULL | - | Client |
| `assigned_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Assigner |
| `assigned_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Assignment timestamp |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `notes` | TextField | Nullable | NULL | Notes |

**Constraints:**
- Unique Together: `('staff', 'client')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `client_id`, `assigned_at`, `is_active`
- Composite: `staff+is_active`, `client+is_active`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `client` → `Client` (CASCADE)
- Foreign Key: `assigned_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **staff/0003_staffclientassignment_staffprogramassignment_and_more.py**
  - Created StaffClientAssignment model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `client`, `assigned_by`, `assigned_at`, `is_active`, `notes`
  - Added unique together constraint: `('staff', 'client')`
  - Added indexes: `staff+is_active`, `client+is_active`

---

### staff_program_assignments

**Table Name:** `staff_program_assignments`  
**Model:** `staff.StaffProgramAssignment`  
**Description:** Assigns staff members to specific programs.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `staff` | ForeignKey(Staff) | Indexed, NOT NULL | - | Staff member |
| `program` | ForeignKey(Program) | Indexed, NOT NULL | - | Program |
| `assigned_by` | ForeignKey(Staff) | Nullable, Indexed | NULL | Assigner |
| `assigned_at` | DateTimeField | Indexed, NOT NULL | `auto_now_add` | Assignment timestamp |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `notes` | TextField | Nullable | NULL | Notes |

**Constraints:**
- Unique Together: `('staff', 'program')`

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `staff_id`, `program_id`, `assigned_at`, `is_active`
- Composite: `staff+is_active`, `program+is_active`

**Relationships:**
- Foreign Key: `staff` → `Staff` (CASCADE)
- Foreign Key: `program` → `Program` (CASCADE)
- Foreign Key: `assigned_by` → `Staff` (SET_NULL, nullable)

#### Migration History

- **staff/0003_staffclientassignment_staffprogramassignment_and_more.py**
  - Created StaffProgramAssignment model with: `id`, `external_id`, `created_at`, `updated_at`, `staff`, `program`, `assigned_by`, `assigned_at`, `is_active`, `notes`
  - Added unique together constraint: `('staff', 'program')`
  - Added indexes: `staff+is_active`, `program+is_active`

---

## Reports App Tables

### report_templates

**Table Name:** `report_templates`  
**Model:** `reports.ReportTemplate`  
**Description:** Report templates with SQL queries and parameters.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `name` | CharField(255) | Unique, NOT NULL | - | Template name |
| `description` | TextField | NOT NULL | - | Description |
| `report_type` | CharField(50) | Indexed, NOT NULL | - | Report type |
| `query_sql` | TextField | NOT NULL | - | SQL query |
| `parameters` | JSONField | NOT NULL | `{}` | Parameters JSON |
| `is_active` | BooleanField | Indexed, NOT NULL | True | Active status |
| `created_by` | ForeignKey(Staff) | Indexed, NOT NULL | - | Creator |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`, `name`
- Indexed: `report_type`, `is_active`, `created_by_id`

**Relationships:**
- Foreign Key: `created_by` → `Staff` (CASCADE)
- Reverse: `reportexecution_set` from ReportExecution

#### Migration History

- **reports/0001_initial.py**
  - Created ReportTemplate model with: `id`, `external_id`, `created_at`, `updated_at`, `name`, `description`, `report_type`, `query_sql`, `parameters`, `is_active`, `created_by`
  - Added indexes: `report_type`, `is_active`, `created_by`

---

### report_executions

**Table Name:** `report_executions`  
**Model:** `reports.ReportExecution`  
**Description:** Execution history for report templates.

#### Final Schema

| Field Name | Type | Constraints | Default | Description |
|------------|------|-------------|---------|-------------|
| `id` | BigAutoField | Primary Key | - | Internal database ID |
| `external_id` | UUIDField | Unique, Indexed | `uuid.uuid4()` | External identifier |
| `created_at` | DateTimeField | NOT NULL | `auto_now_add` | Record creation timestamp |
| `updated_at` | DateTimeField | NOT NULL | `auto_now` | Record update timestamp |
| `template` | ForeignKey(ReportTemplate) | Indexed, NOT NULL | - | Report template |
| `executed_by` | ForeignKey(Staff) | Indexed, NOT NULL | - | Executor |
| `parameters_used` | JSONField | NOT NULL | `{}` | Parameters used |
| `status` | CharField(20) | Indexed, NOT NULL | - | Execution status |
| `result_file_url` | URLField(500) | Nullable | NULL | Result file URL |
| `error_message` | TextField | Nullable | NULL | Error message |
| `execution_time` | DurationField | Nullable | NULL | Execution duration |

**Indexes:**
- Primary Key: `id`
- Unique: `external_id`
- Indexed: `template_id`, `executed_by_id`, `status`, `created_at`
- Composite: `template+executed_by`, `status`, `created_at`

**Relationships:**
- Foreign Key: `template` → `ReportTemplate` (CASCADE)
- Foreign Key: `executed_by` → `Staff` (CASCADE)

#### Migration History

- **reports/0001_initial.py**
  - Created ReportExecution model with: `id`, `external_id`, `created_at`, `updated_at`, `template`, `executed_by`, `parameters_used`, `status`, `result_file_url`, `error_message`, `execution_time`
  - Added indexes: `template+executed_by`, `status`, `created_at`

---

## Summary Statistics

### Total Tables: 37

**By App:**
- **Core App:** 25 tables
- **Clients App:** 2 tables (models defined, tables removed)
- **Programs App:** 3 tables
- **Staff App:** 5 tables
- **Reports App:** 2 tables

### Common Patterns

1. **BaseModel Fields:** Most tables inherit from `BaseModel` with:
   - `id` (BigAutoField, Primary Key)
   - `external_id` (UUIDField, Unique, Indexed)
   - `created_at` (DateTimeField, auto_now_add)
   - `updated_at` (DateTimeField, auto_now)

2. **Archiving Pattern:** Many tables support soft-deletion:
   - `is_archived` (BooleanField, default=False, indexed)
   - `archived_at` (DateTimeField, nullable, indexed)

3. **Audit Fields:** Many tables track who created/updated:
   - `created_by` (CharField or ForeignKey to Staff)
   - `updated_by` (CharField)

4. **Active Status:** Many assignment/relationship tables have:
   - `is_active` (BooleanField, default=True, indexed)

---

## Migration Summary by Date

### 2025-09-04 (Initial)
- Created core models: User, Department, Role, Staff, StaffRole, Program, ProgramStaff, Client, ClientProgramEnrollment, Intake, Discharge, ServiceRestriction, AuditLog, PendingChange

### 2025-09-12
- Created ClientNote, ClientContact, ClientDocument (clients app)

### 2025-09-22
- Created ClientDuplicate model

### 2025-09-30
- Created ProgramServiceManagerAssignment, ProgramManagerAssignment

### 2025-10-03
- Enhanced ServiceRestriction with behaviors, notes, indefinite flag

### 2025-10-10
- Added Bill 168 and No Trespass fields to ServiceRestriction

### 2025-10-14
- Created DepartmentLeaderAssignment model

### 2025-10-16
- Created EmailRecipient and EmailLog models

### 2025-10-17
- **Removed** ClientNote, ClientContact, ClientDocument tables (clients app)

### 2025-11-03
- Created ClientUploadLog model

### 2025-11-05
- Added archiving fields (`is_archived`, `archived_at`) to Client, Department, Program, ClientProgramEnrollment, ServiceRestriction

### 2025-11-XX (Recent)
- Created ServiceRestrictionNotificationSubscription
- Created Notification model
- Added legacy client IDs support
- Added detection source to ClientDuplicate
- Added affected staff to ServiceRestriction

---

## Notes

1. **ClientNote and ClientContact:** Models are defined in `clients/models.py` but tables were removed in migration 0004. To restore, create a new migration.

2. **Pending Changes:** The `pending_changes` table exists but may not be actively used in the current application.

3. **Archiving:** Most major entities (Client, Department, Program, Enrollment, ServiceRestriction) support soft-deletion via `is_archived` and `archived_at` fields.

4. **Legacy Support:** The Client model includes extensive legacy field support for backward compatibility with SMIS, EMHware, and FFAI systems.

5. **Migration Naming:** Some migrations have non-standard naming (e.g., 0036-0040 all deal with restriction_type conversion).

---

**Document Generated:** 2025-11-18  
**Total Migrations Analyzed:** 78 core migrations + migrations from other apps  
**Database Engine:** PostgreSQL  
**Django Version:** 4.2.7


