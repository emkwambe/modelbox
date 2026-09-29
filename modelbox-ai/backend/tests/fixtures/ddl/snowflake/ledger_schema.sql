-- ModelBox DDL fixture: DOCUMENTATION-DERIVED. Hand-written, not tool output; no Snowflake account produced it.
-- provenance: documentation-derived
-- source: Snowflake documentation, GET_DDL (https://docs.snowflake.com/en/sql-reference/functions/get_ddl), retrieved 2026-09-29. Written in the output shapes its examples show: GET_DDL('SCHEMA', ...) for the schema, standard tables and the view, and GET_DDL('TABLE', ...) of a hybrid table for NOT NULL and the primary key line. Table and column names are our own.
-- not covered: the page shows no GET_DDL output with foreign keys, unique constraints or comments, so this fixture has none
-- certification: Snowflake import is not certified while this fixture is documentation-derived
-- end of provenance
CREATE OR REPLACE SCHEMA LEDGER_SCHEMA;

CREATE OR REPLACE TABLE BRANCHES (
	ID NUMBER(38,0),
	BRANCH_NAME VARCHAR(255),
	REGION VARCHAR(64)
);

CREATE OR REPLACE TABLE TRANSACTIONS (
	ID NUMBER(38,0),
	ACCOUNT_ID NUMBER(38,0),
	POSTED_AT TIMESTAMP_NTZ(9),
	AMOUNT NUMBER(18,2),
	CURRENCY VARCHAR(3)
);

CREATE OR REPLACE VIEW BRANCH_NAMES_VIEW as select branch_name, region from branches;

create or replace HYBRID TABLE ACCOUNTS (
  ID NUMBER(38,0) NOT NULL,
  OPENED_AT TIMESTAMP_NTZ(9),
  BALANCE NUMBER(18,2),
  BRANCH_ID NUMBER(38,0),
  STATUS VARCHAR(20),
  primary key (ID)
);
