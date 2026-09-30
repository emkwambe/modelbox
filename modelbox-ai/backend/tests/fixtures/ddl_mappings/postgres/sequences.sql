-- Synthetic, written by hand for the sequence mapping, PostgreSQL to PostgreSQL (see ../README.md). Not tool output.

CREATE SEQUENCE public.invoice_no_seq
    START WITH 1000
    INCREMENT BY 5
    MINVALUE 1000
    MAXVALUE 999999
    CACHE 1;

CREATE TABLE public.invoice (
    invoice_no integer DEFAULT nextval('public.invoice_no_seq'::regclass) NOT NULL,
    amount numeric(12,2) NOT NULL,
    CONSTRAINT invoice_pkey PRIMARY KEY (invoice_no)
);
