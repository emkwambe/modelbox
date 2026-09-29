-- Drift applied to Oracle HR after its fixture is exported (Sprint 8 Step 5).
-- ddl-fixtures.yml runs this as HR against the real database, then exports
-- HR again with the same exporter into backend/tests/fixtures/ddl_drift/oracle.
-- Each statement is numbered; hr.expected.json names the drift each one makes,
-- written from this script, not from ModelBox's output.

-- 1. A table added.
CREATE TABLE skills (skill_id NUMBER(6) CONSTRAINT skills_pk PRIMARY KEY, skill_name VARCHAR2(40) NOT NULL);
-- 2. A NOT NULL column added with a default.
ALTER TABLE departments ADD (is_active CHAR(1) DEFAULT 'Y' NOT NULL);
-- 3. A type widened.
ALTER TABLE locations MODIFY (city VARCHAR2(40));
-- 4. A type narrowed (the longest job title in the data is 31 characters).
ALTER TABLE jobs MODIFY (job_title VARCHAR2(32));
-- 5. A NOT NULL column made nullable.
ALTER TABLE employees MODIFY (email NULL);
-- 6. A default added.
ALTER TABLE employees MODIFY (hire_date DEFAULT SYSDATE);
-- 7. A column removed.
ALTER TABLE employees DROP COLUMN commission_pct;
-- 8. A CHECK constraint removed.
ALTER TABLE employees DROP CONSTRAINT emp_salary_min;
-- 9. A UNIQUE constraint removed.
ALTER TABLE employees DROP CONSTRAINT emp_email_uk;
-- 10. A composite UNIQUE constraint added.
ALTER TABLE employees ADD CONSTRAINT emp_full_name_uk UNIQUE (first_name, last_name);
-- 11. A CHECK constraint added.
ALTER TABLE jobs ADD CONSTRAINT job_salary_range_chk CHECK (min_salary <= max_salary);
-- 12. A foreign key removed.
ALTER TABLE locations DROP CONSTRAINT loc_c_id_fk;
-- 13. A composite primary key changed (13a and 13b are one drift).
ALTER TABLE job_history DROP PRIMARY KEY;
ALTER TABLE job_history ADD CONSTRAINT jhist_emp_st_end_pk PRIMARY KEY (employee_id, start_date, end_date);
-- 14. A column renamed: reported as a removal and an addition, never as a rename.
ALTER TABLE locations RENAME COLUMN street_address TO address_line;
-- 15. A table description changed.
COMMENT ON TABLE regions IS 'Regions of the world, by number and name.';
-- 16. A column description removed.
COMMENT ON COLUMN regions.region_name IS '';
