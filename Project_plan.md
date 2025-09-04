# 📌 Central Client Database (CCD) – Developer Build Spec

---

[PPT.pptx](attachment:3c564dee-3fb2-4ba9-a0ef-e1fd4977ce0c:PPT.pptx)

[Task Breakdown](https://www.notion.so/Task-Breakdown-25d415496f0880fa9811d902e9502ca8?pvs=21)

**Tech Stack**

* **Backend:** Django (Python 3.11+)
* **Frontend:** Django templates + TailwindCSS
* **Database:** PostgreSQL 15
* **Deployment:** Docker + docker-compose, Gunicorn, pg_dump for backups

---

## 1. Database Schema (Postgres)

### 1.1 Departments

* `department_id` (UUID, PK)
* `name` (string, unique, case-insensitive)
* `owner` (string, nullable)
* `created_at`, `updated_at`

Constraints:

* Unique lowercased department name.
  Relationships:
* One-to-many with Programs.

---

### 1.2 Programs & Services (combined)

* `program_id` (UUID, PK)
* `name` (string)
* `department_id` (FK → Departments)
* `location` (string; one location for now, future-proof to multi-location later)
* `capacity_current` (integer; manually configured by Coordinator)
* `capacity_effective_date` (date, nullable)
* `created_at`, `updated_at`

Notes:

* Programs may have  **multiple staff** , including multiple managers.
* Consider adding `program_type` field in future if programs vs. services need separation.

---

### 1.3 Staff

* `staff_id` (UUID, PK)
* `first_name`, `last_name`
* `email` (unique, case-insensitive)
* `active` (boolean)
* `created_at`, `updated_at`

### 1.4 Roles

* `role_id` (UUID, PK)
* `name` (string, unique)
  * Roles: Administrator, Staff, Manager, Leader, Analyst

### 1.5 StaffRoles (M2M)

* `staff_id` (FK → Staff)
* `role_id` (FK → Roles)
* Composite PK: `(staff_id, role_id)`

Relationships:

* One staff can have multiple roles.

---

### **1.6 Clients**

* client_id (UUID, PK)
* first_name (string)
* last_name (string)
* preferred_name (string, nullable)
* alias (string, nullable)
* dob (date of birth)
* gender (string)
* sexual_orientation (string)
* languages_spoken (array/text, multiple allowed)
* race (string)
* immigration_status (string dropdown; e.g., refugee, permanent resident, citizen, etc.)
* image (string/filepath/URL to profile image, nullable)
* phone_number (string, nullable)
* email (string, unique if possible, nullable)
* address (string or JSON for structured address, nullable)
* uid_external (string, unique if available, for linking to SMIS/EMHWare/FFAI)
* created_at, updated_at (timestamps)

Notes:

* This table must support all demographics required for reporting: gender, sexual orientation, race, immigration status, languages, etc.
* Fields like preferred_name and alias should be nullable but searchable.
* address can later be normalized into a separate addresses table if multiple addresses per client are needed.
* image can be stored as a URL (if integrated with S3/Azure Blob) or file path.

---

### 1.7 Enrollments

**ClientProgramEnrollments**

* `enrollment_id` (UUID, PK)
* `client_id` (FK → Clients)
* `program_id` (FK → Programs)
* `start_date`, `end_date` (nullable)
* Constraint: `end_date >= start_date`
* Clients can have  **multiple concurrent enrollments** .

---

### 1.8 Intakes

* `intake_id` (UUID, PK)
* `client_id` (FK → Clients)
* `program_id` (FK → Programs)
* `intake_date`
* `source_system` (string; e.g., SMIS, EMHWare)

---

### 1.9 Discharges

* `discharge_id` (UUID, PK)
* `client_id`, `program_id`
* `discharge_date`
* `reason`

---

### 1.10 Service Restrictions

* `restriction_id` (UUID, PK)
* `client_id` (FK → Clients)
* `scope` (enum: `org`, `program`)
* `program_id` (nullable FK → Programs; required if scope=program)
* `start_date`, `end_date` (nullable)
* `reason`

Constraints:

* `(scope='org' AND program_id IS NULL)` OR `(scope='program' AND program_id IS NOT NULL)`
  Notes:
* Historical data must be retained for at least  **10 years** .

---

### 1.11 Audit Log

* `audit_id` (UUID, PK)
* `entity` (string, e.g., `clients`)
* `entity_id` (UUID)
* `action` (string: `create`, `update`, `delete`, `import`)
* `changed_by` (FK → Staff, nullable)
* `changed_at` (timestamp)
* `diff_json` (JSON: before/after snapshot)

---

### 1.12 Pending Changes (Approval Workflow)

* `change_id` (UUID, PK)
* `entity` (string)
* `entity_id` (UUID)
* `diff_json` (JSON of proposed change)
* `requested_by` (FK → Staff)
* `status` (enum: `pending`, `approved`, `declined`)
* `reviewed_by` (FK → Staff, nullable)
* `reviewed_at` (timestamp, nullable)
* `rationale` (string, nullable)

---

## 2. Backend Flows (Django)

### 2.1 Role-based Permissions

* **Administrator** : full control.
* **Client Data Coordinator** : can approve/decline pending changes; direct edits allowed.
* **Managers/Leaders** :
* Can view and **propose edits** → stored in PendingChanges.
* Cannot directly update canonical tables.
* **Staff** : restricted visibility to assigned clients/programs.
* **Analyst** : read-only (full data, export allowed).

---

### 2.2 Approval Workflow

* **All edits** by Managers/Leaders must go through approval.
* Coordinator approves → apply change to canonical record + AuditLog.
* Decline → rationale recorded.
* Must be atomic: apply diff + log together.

---

### 2.3 Ingestion Workflow (Daily CSV/Excel Import)

* Run via: `manage.py ingest_daily --src /path/to/file.csv --source=SMIS`
* Steps:
  1. Load CSV into staging.
  2. Matching logic:
     * Match on `uid_external` (preferred).
     * If missing: fuzzy dedupe on `(first_name, last_name, dob)`
       * Case-insensitive, trimmed.
       * Future: Postgres trigram / Levenshtein.
     * If multiple candidates → write to rejects CSV for manual review.
  3. Insert/update `clients`, `intakes`, `enrollments`, `discharges`.
  4. Import summary logged in AuditLog (rows inserted/updated/skipped).

---

## 3. Reporting

### 3.1 Organizational Summary Report

* Inputs: `date_from`, `date_to`.
* Outputs:
  * Distinct clients served (deduped across programs).
  * Demographic breakdowns: gender, sexual orientation, immigration status, languages, etc.
  * Drilldowns: by department, by program.
* Exports: CSV.
* Must prevent double-counting if client enrolled in multiple programs.

---

### 3.2 Vacancy Tracker Report

* Inputs: `as_of` date.
* For each program:
  * `capacity_current` (from Programs)
  * `occupied` = count of active enrollments
  * `vacant` = capacity - occupied
* Exports: CSV.

---

## 4. Frontend (Django + TailwindCSS)

### 4.1 Structure

* **Sidebar Navigation** :
* Clients
* Programs & Services
* Departments
* Enrollments
* Restrictions
* Approvals
* Reports
* Audit Log
* **Topbar** : user info + logout.

---

### 4.2 Pages

**Clients**

* Search + list view.
* Detail view → tabs: demographics, intakes, discharges, enrollments, restrictions.
* Add/edit client form with demographics (gender, orientation, immigration status, languages, etc.).

**Programs & Services**

* List of programs with filters.
* Detail view → staff, location, capacity, enrollments.
* Assign multiple staff (including multiple managers).

**Departments**

* CRUD interface.

**Enrollments**

* List per client or program.
* Allow multiple concurrent enrollments.

**Restrictions**

* List active vs expired restrictions.
* Form: scope toggle (org/program), program select, start/end date, reason.
* View 10+ years of restriction history.

**Approvals Inbox**

* List all pending changes.
* Detail page: proposed diff vs current record.
* Actions: approve/decline with rationale.

**Reports**

* Org Summary: filters for date range + demographics. Table view + CSV export.
* Vacancy Tracker: table view by program + CSV export.

**Audit Log**

* Searchable/filterable (by entity, date, user).
* Display diff_json in human-readable format (before/after).

---

## 5. Docker & Deployment

### 5.1 docker-compose.yml

Services:

* `web`: Django + Gunicorn
* `db`: Postgres 15

Volumes:

* Persistent storage for Postgres.

---

### 5.2 Environment (.env)

```
DJANGO_SECRET_KEY=changeme
DATABASE_URL=postgres://ccd:ccdpass@db:5432/ccd
DEBUG=1
ALLOWED_HOSTS=localhost,127.0.0.1

```

---

### 5.3 Backups

* Nightly `pg_dump` to S3/Spaces.
* Retention: **10 years** minimum (to meet historical requirement).

---

## 6. Acceptance Criteria

1. **Clients** can be enrolled in multiple programs at once.
2. **Service Restrictions** work at both org and program level; history is retained ≥10 years.
3. **Approval Workflow** : all Manager/Leader edits create pending changes; Coordinator can approve/decline.
4. **Reports** :

* Org Summary shows unique client counts with demographic breakdowns.
* Vacancy Tracker shows capacity, occupied, vacant per program.
* Both exportable as CSV.

1. **Audit Log** : every edit (manual, approved, import) is logged with before/after.
2. **Ingestion** : daily CSV import updates data; fuzzy dedupe logic works; rejects file produced if match uncertain.

---
