-- Drift applied to Pagila after its fixture is exported (Sprint 8 Step 5).
-- ddl-fixtures.yml runs this against the real database, then dumps it again
-- with the same exporter into backend/tests/fixtures/ddl_drift/postgres.
-- Each statement is numbered; pagila.expected.json names the drift each one
-- makes, written from this script, not from ModelBox's output. Pagila is
-- loaded schema-only, so no table has rows; no column changed here is read by
-- one of its views.

-- 1. A table added.
CREATE TABLE public.loyalty_tier (tier_id integer NOT NULL, name text NOT NULL, CONSTRAINT loyalty_tier_pkey PRIMARY KEY (tier_id));
-- 2. A nullable column added.
ALTER TABLE public.customer ADD COLUMN loyalty_tier_id integer;
-- 3. A foreign key added.
ALTER TABLE public.customer ADD CONSTRAINT customer_loyalty_tier_id_fkey FOREIGN KEY (loyalty_tier_id) REFERENCES public.loyalty_tier(tier_id);
-- 4. A NOT NULL column added with no default.
ALTER TABLE public.language ADD COLUMN iso_code character(2) NOT NULL;
-- 5. A default changed.
ALTER TABLE public.film ALTER COLUMN rental_duration SET DEFAULT 5;
-- 6. A type widened.
ALTER TABLE public.film ALTER COLUMN replacement_cost TYPE numeric(7,2);
-- 7. A type narrowed.
ALTER TABLE public.staff ALTER COLUMN username TYPE character varying(16);
-- 8. A NOT NULL column made nullable.
ALTER TABLE public.store ALTER COLUMN last_update DROP NOT NULL;
-- 9. A nullable column made NOT NULL.
ALTER TABLE public.staff ALTER COLUMN email SET NOT NULL;
-- 10. A column removed.
ALTER TABLE public.customer DROP COLUMN create_date;
-- 11. A column renamed: reported as a removal and an addition, never as a rename.
ALTER TABLE public.address RENAME COLUMN address2 TO address_line2;
-- 12. A foreign key removed.
ALTER TABLE public.store DROP CONSTRAINT store_address_id_fkey;
-- 13. A composite UNIQUE constraint added.
ALTER TABLE public.customer ADD CONSTRAINT customer_store_email_key UNIQUE (store_id, email);
-- 14. A CHECK constraint added.
ALTER TABLE public.film ADD CONSTRAINT film_length_positive CHECK (length > 0);
-- 15. A column description added.
COMMENT ON COLUMN public.actor.first_name IS 'Given name of the actor.';
-- 16. A table description added.
COMMENT ON TABLE public.category IS 'Film genres.';
