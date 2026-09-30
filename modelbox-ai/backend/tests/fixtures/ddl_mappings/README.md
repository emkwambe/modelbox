# Type, identity and sequence mapping cases

**Synthetic, written by hand.** Not tool output, and not a certification
fixture: the genuine exports are in `../ddl/`. Each file holds one case per
mapping the PostgreSQL export makes from its dialect. Each file is written in
the form that dialect's export tool writes, so the importer reads it on the
same path as a genuine file.

| File | Cases |
|---|---|
| `tsql/type_mappings.sql` | `money`, `smallmoney`, `bit` with its defaults and a CHECK over it, an `int` and a `bigint` `IDENTITY(seed, increment)`, `hierarchyid` and `geography` |
| `oracle/identity.sql` | a `NUMBER(*,0)` identity `BY DEFAULT ON NULL` with its sequence options, an `INTEGER` identity `GENERATED ALWAYS`, and a column a `BEFORE INSERT` trigger fills from a sequence |
| `postgres/sequences.sql` | a sequence with every option set, and a column whose default calls it |
| `tsql/computed_columns.sql` | AdventureWorks' computed-column expressions over columns of the same types: a string concatenation, money and decimal arithmetic, integer arithmetic, a `PERSISTED` column, and a call to a function the file does not define |

`test_type_mappings.py` checks what each case exports to. `test_type_mappings_on_postgres.py`
applies each export to a real PostgreSQL, and to a PostGIS image pinned by
digest for `geography`. It then reads the result back from the catalog, and
inserts rows that the constraints must accept or refuse.
