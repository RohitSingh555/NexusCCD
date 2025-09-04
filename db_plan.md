---


---
## 🗂 Database (Postgres)

**Ticket 1: Create Departments Table**

* Fields:
  * `department_id` (UUID, PK)
  * `name` (string, unique, case-insensitive)
  * `owner` (string, nullable)
  * `created_at`, `updated_at` (timestamps)
* Constraints:
  * Unique on lowercase `name`.
* Relationships:
  * One-to-many with Programs.

---

**Ticket 2: Create Programs & Services Table**

* Combined “Programs & Services” (per Vaibhav’s clarification).
* Fields:
  * `program_id` (UUID, PK)
  * `name` (string)
  * `department_id` (FK → Departments)
  * `location` (string; single for now, scalable later)
  * `capacity_current` (integer, nullable)
  * `capacity_effective_date` (date, nullable)
  * `created_at`, `updated_at`
* Relationships:
  * Many-to-many with Staff (via junction table).
  * Belongs to one Department.
* Notes:
  * More than one staff per program.
  * More than one manager allowed.

---

**Ticket 3: Create Staff & Roles Tables**

* **Staff Table** :
* `staff_id` (UUID, PK)
* `first_name`, `last_name`
* `email` (unique, case-insensitive)
* `active` (boolean)
* `created_at`, `updated_at`
* **Roles Table** :
* `role_id` (UUID, PK)
* `name` (enum-like: Administrator, Staff, Manager, Leader, Analyst)
* **StaffRoles Junction Table** :
* `staff_id` (FK → Staff)
* `role_id` (FK → Roles)
* Composite PK (staff_id, role_id)

---

**Ticket 4: Create Clients Table**

* Fields:
  * `client_id` (UUID, PK)
  * `first_name`, `last_name`
  * `dob` (date)
  * `gender` (string)
  * `languages` (array/text)
  * `sexual_orientation` (string)
  * `immigration_status` (string, dropdown values; refugee included here)
  * `uid_external` (string, for linking to SMIS/EMH/FFAI)
  * `created_at`, `updated_at`
* Notes:
  * Must allow extension (other demographics may be added).

---

**Ticket 5: Create Enrollment, Intake, Discharge Tables**

* **ClientProgramEnrollments** :
* `enrollment_id` (UUID, PK)
* `client_id` (FK → Clients)
* `program_id` (FK → Programs)
* `start_date`, `end_date` (nullable)
* Constraint: `end_date >= start_date`
* Notes: multiple concurrent enrollments allowed.
* **Intakes** :
* `intake_id` (UUID, PK)
* `client_id`, `program_id`
* `intake_date`
* `source_system` (string)
* **Discharges** :
* `discharge_id` (UUID, PK)
* `client_id`, `program_id`
* `discharge_date`
* `reason`

---

**Ticket 6: Create ServiceRestrictions Table**

* Fields:
  * `restriction_id` (UUID, PK)
  * `client_id` (FK → Clients)
  * `scope` (enum: `org`, `program`)
  * `program_id` (nullable FK → Programs; required if scope=program)
  * `start_date`, `end_date` (nullable)
  * `reason`
* Constraints:
  * `(scope='org' AND program_id IS NULL)` OR `(scope='program' AND program_id IS NOT NULL)`
* Notes:
  * Retain historical restrictions (≥ 10 years).

---

**Ticket 7: Create Audit & PendingChanges Tables**

* **AuditLog** :
* `audit_id` (UUID, PK)
* `entity` (string)
* `entity_id` (UUID)
* `action` (string: create/update/delete)
* `changed_by` (FK → Staff, nullable)
* `changed_at` (timestamp)
* `diff_json` (JSON)
* **PendingChanges** :
* `change_id` (UUID, PK)
* `entity`, `entity_id`
* `diff_json` (JSON of proposed change)
* `requested_by` (FK → Staff)
* `status` (enum: pending/approved/declined)
* `reviewed_by` (FK → Staff, nullable)
* `reviewed_at` (timestamp, nullable)
* `rationale` (string, nullable)

---

## ⚙️ Backend (Django)

**Ticket 8: Implement Role-based Permissions**

* Map staff to roles.
* Enforce:
  * Managers/Leaders → create pending changes only.
  * Coordinators → approve/decline changes, direct edits.
  * Analysts → read-only.
  * Admin → full control.

---

**Ticket 9: Approval Workflow Implementation**

* All edits (any entity) from Managers/Leaders → stored in `PendingChanges`.
* Coordinator UI: approve → apply update + AuditLog; decline → mark with rationale.
* Changes applied via transaction.

---

**Ticket 10: Ingestion Workflow (Daily Import)**

* Management command: `manage.py ingest_daily --src <file.csv> --source=SMIS`
* Steps:
  1. Load CSV into staging.
  2. Match logic:
     * Direct match via `uid_external`.
     * Else fuzzy match: `first_name + last_name + dob`.
       * Case-insensitive, trimmed.
       * Future: trigram/Levenshtein.
     * Ambiguous → flagged in “rejects” CSV.
  3. Insert or update clients, enrollments, intakes/discharges.
  4. Write summary log (rows inserted/updated/skipped) to AuditLog.

---

## 📊 Reporting

**Ticket 11: Org Summary Report**

* Inputs: `date_from`, `date_to`.
* Output:
  * Distinct client count (no double counting).
  * Demographics: gender, sexual orientation, immigration status, languages, etc.
  * Breakdowns: by department, by program.
* Export: CSV.

---

**Ticket 12: Vacancy Tracker Report**

* Inputs: `as_of` date.
* Per program:
  * `capacity_current`
  * `occupied` = active enrollments
  * `vacant` = capacity - occupied
* Export: CSV.

---

## 🎨 Frontend (Django + Tailwind)

**Ticket 13: Navigation Structure**

* Sidebar with:
  * Clients
  * Programs & Services
  * Departments
  * Enrollments
  * Restrictions
  * Approvals
  * Reports
  * Audit Log
* Topbar: user profile + logout.

---

**Ticket 14: Clients Module (UI)**

* List + search.
* Detail view with tabs: demographics, intakes, discharges, enrollments, restrictions.
* Add/edit form: demographic fields (gender, languages, immigration, orientation, etc.).

---

**Ticket 15: Programs Module (UI)**

* List all programs.
* Detail: show staff, location, capacity, enrollments.
* Allow multiple staff per program.

---

**Ticket 16: Restrictions Module (UI)**

* List active vs expired.
* Form: scope (org/program), program selection, start/end dates, reason.
* Historical restrictions list (10+ years).

---

**Ticket 17: Approvals Inbox (UI)**

* List pending changes.
* Detail: show proposed change vs current record.
* Actions: approve, decline (with rationale).

---

**Ticket 18: Reports (UI)**

* Org Summary: date pickers + table view, CSV export button.
* Vacancy Tracker: table view of programs, CSV export button.

---

**Ticket 19: Audit Log (UI)**

* Searchable table: filter by entity, date, user.
* Show diff_json nicely (before/after).

---

## 🐳 Docker & Deployment

**Ticket 20: Dockerize Application**

* `docker-compose.yml` with services:
  * `web`: Django + Gunicorn
  * `db`: Postgres 15
* Mount volumes for persistence.
* Environment variables in `.env`.

---

**Ticket 21: Database Backups**

* Nightly `pg_dump` to S3/Spaces.
* Retention policy ≥ 10 years.

---

✅ That’s **21 tickets** with detailed scope, grouped logically.
