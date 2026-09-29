# DDL fixtures: genuine tool exports

Every `.sql` file here was written by a database's own export tool, run in CI
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

The DDL describes the sample schemas it was exported from, both published
under the MIT licence.

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
