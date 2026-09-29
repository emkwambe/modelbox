# DDL fixtures: genuine tool exports

Every `.sql` file here except `snowflake/` was written by a database's own export tool, run in CI
by `.github/workflows/ddl-fixtures.yml` against a real database loaded with a
public sample schema. None is hand-written or edited. That workflow regenerates
them whenever the generators or these files change, and fails unless the
committed copies match what the tools produce (only the generation date and
run may differ). To change a fixture, change the generator and commit what the
workflow uploads.

Each `.sql` opens with a provenance header naming the source, the tool and its
version, the image digest, and the date and run that produced it. Beside it,
`<name>.manifest.json` holds the counts an import must reconcile against:
tables, columns, primary keys, foreign keys, UNIQUE and CHECK constraints, and
table and column descriptions, in total and per table. **The counts are read
from the source database's catalog views, never from a parser**, so they are
independent of the code they check. `tests/test_ddl_fixtures.py` holds the
header and manifest rules.

| Fixture | Source | Tool |
| :-- | :-- | :-- |
| `oracle/hr.sql` | Oracle sample schema HR (`human_resources/hr_create.sql`) | `DBMS_METADATA.GET_DDL`, default transform parameters with `SQLTERMINATOR` on, plus `GET_DEPENDENT_DDL('COMMENT')` |
| `oracle/co.sql` | Oracle sample schema CO (`customer_orders/co_create.sql`) | as above |
| `tsql/adventureworks.sql` | AdventureWorks2022 (Microsoft's `.bak` release) | SMO Scripter, the engine behind SSMS's scripting, with SSMS's defaults for tables |
| `postgres/pagila.sql` | Pagila (`pagila-schema.sql`), at the last commit that loads on PostgreSQL 16 | `pg_dump --schema-only` from the appliance's own pinned PostgreSQL 16.15 image, with a fixed `--restrict-key` (otherwise random per run) |
| `snowflake/ledger_schema.sql` | **Documentation-derived, hand-written** | none: written in the output shapes of Snowflake's `GET_DDL` documentation, because no Snowflake account runs in CI |

**The Snowflake fixture is the one exception to "genuine tool output".** Its
header and manifest both say `documentation-derived`, its manifest counts are
read from the file itself (so they check nothing independently), and it holds
only what the `GET_DDL` page shows: no foreign keys, unique constraints or
comments, whose output that page never shows. `tests/test_ddl_fixtures.py`
fails if the label is removed, or if the docs, the application or the frontend
call Snowflake import certified while it stands.

**What the PostgreSQL fixture holds.** Everything `pg_dump --schema-only`
writes: tables, 55 partitions of `payment`, sequences, views, a materialized
view, functions, triggers, domains and a type. Its manifest counts every
constraint the catalog holds on each table, and separately those a partition
inherits from its parent: `pg_dump` writes each partition's inherited primary
key as its own `ADD CONSTRAINT` (55 of the dump's 70), so an importer meets
them in the text. In Pagila no foreign key is inherited; the 18 on partitions
are declared there. A `PRIMARY KEY` inside a function body and a `CHECK` on a
domain are in the text too, and are not table constraints.

**What the SQL Server fixture holds.** Schemas, user-defined data types, and
every user table with its keys, defaults, checks, foreign keys, indexes and
extended properties, each statement followed by `GO`, as SSMS scripts them.
Triggers, collation and SSMS's timestamped object headers are off. SSMS saves
files as UTF-16 by default; this one is UTF-8, so an importer must not assume
either.

**What the Oracle fixtures hold.** Tables with their constraints and comments.
Indexes created separately, sequences, views and procedural code are not
exported; the manifests count only tables and what belongs to them.

## Licences

The DDL describes the sample schemas it was exported from. The Oracle, SQL
Server and PostgreSQL sources are published under the MIT licence; Pagila is a
port of MySQL's Sakila, whose schema is under the New BSD licence. The
Snowflake fixture is our own text.

**Pagila** (`devrimgunduz/pagila`, `LICENSE.txt`; its README also describes it
as "made available under PostgreSQL license"):

> Copyright (c) Devrim Gündüz <devrim@gunduz.org>
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
> THE SOFTWARE.

**Sakila**, from which Pagila was ported (`sakila-schema.sql`, MySQL's
`sakila-db` download; "The contents of the sakila-schema.sql and sakila-data.sql
files are licensed under the New BSD license"):

> Copyright (c) 2006, 2026, Oracle and/or its affiliates.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are
> met:
>
> * Redistributions of source code must retain the above copyright notice,
>   this list of conditions and the following disclaimer.
> * Redistributions in binary form must reproduce the above copyright
>   notice, this list of conditions and the following disclaimer in the
>   documentation and/or other materials provided with the distribution.
> * Neither the name of Oracle nor the names of its contributors may be used
>   to endorse or promote products derived from this software without
>   specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
> IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
> THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
> PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
> CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
> EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
> PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
> PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
> LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
> NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
> SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

**Oracle sample schemas** (`oracle-samples/db-sample-schemas`):

> Copyright (c) 2023 Oracle and/or its affiliates. All rights reserved.
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

**Microsoft SQL Server Sample Code** (`microsoft/sql-server-samples`,
AdventureWorks):

> Microsoft SQL Server Sample Code
>
> Copyright (c) Microsoft Corporation
>
> All rights reserved.
>
> MIT License.
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
> THE SOFTWARE.
