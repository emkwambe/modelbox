#Requires -Version 7
<#
.SYNOPSIS
Script AdventureWorks the way SSMS does, with SMO, and count it from the catalog.

.DESCRIPTION
Runs in CI (.github/workflows/ddl-fixtures.yml) against a SQL Server container
into which AdventureWorks was restored. SSMS's "Script Table As" and "Generate
Scripts" are both SMO's Scripter; this uses the same library, with SSMS's
default choices for tables: DRI (keys, defaults, checks, foreign keys),
indexes and extended properties on, triggers and collation off. Each object's
statements are separated by GO, as SSMS writes them. Schemas and user-defined
data types come first, as Generate Scripts orders them.

Two files are written:
  adventureworks.sql            the scripted DDL, with a provenance header
  adventureworks.manifest.json  counts read from the sys catalog views, never
                                from a parser

The sa password comes from MSSQL_SA_PASSWORD; it is never printed.
#>
param(
    [Parameter(Mandatory)] [string] $Server,
    [Parameter(Mandatory)] [string] $Database,
    [Parameter(Mandatory)] [string] $Out,
    [Parameter(Mandatory)] [string] $Image,
    [Parameter(Mandatory)] [string] $Source,
    [Parameter(Mandatory)] [string] $Run
)

$ErrorActionPreference = 'Stop'
Import-Module SqlServer -RequiredVersion 22.4.5.1

$connection = New-Object Microsoft.SqlServer.Management.Common.ServerConnection
$connection.ConnectionString = "Server=$Server;Database=$Database;User ID=sa;Password=$($env:MSSQL_SA_PASSWORD);TrustServerCertificate=True;Encrypt=False"
$smo = New-Object Microsoft.SqlServer.Management.Smo.Server $connection
$db = $smo.Databases[$Database]
if (-not $db) { throw "database $Database not found" }

$options = New-Object Microsoft.SqlServer.Management.Smo.ScriptingOptions
$options.DriAll = $true
$options.Indexes = $true
$options.ExtendedProperties = $true
$options.Triggers = $false
$options.NoCollation = $true
$options.SchemaQualify = $true
$options.IncludeHeaders = $false   # the SSMS header carries a timestamp; the provenance header records the date
$options.AnsiPadding = $false

$statements = [System.Collections.Generic.List[string]]::new()
function Add-Scripted($object) {
    foreach ($statement in $object.Script($options)) { $statements.Add($statement) }
}

foreach ($schema in ($db.Schemas | Where-Object { -not $_.IsSystemObject } | Sort-Object Name)) {
    Add-Scripted $schema
}
foreach ($type in ($db.UserDefinedDataTypes | Sort-Object Schema, Name)) {
    Add-Scripted $type
}
$tables = @($db.Tables | Where-Object { -not $_.IsSystemObject } | Sort-Object Schema, Name)
foreach ($table in $tables) {
    Add-Scripted $table
}

# Counts, per table, from the catalog. Descriptions are MS_Description extended
# properties on the table (minor_id 0) or its columns (minor_id > 0).
$perTable = @"
SELECT s.name AS [schema], t.name AS [table],
       (SELECT COUNT(*) FROM sys.columns c WHERE c.object_id = t.object_id) AS columns,
       (SELECT COUNT(*) FROM sys.key_constraints k WHERE k.parent_object_id = t.object_id AND k.type = 'PK') AS primary_keys,
       (SELECT COUNT(*) FROM sys.foreign_keys f WHERE f.parent_object_id = t.object_id) AS foreign_keys,
       (SELECT COUNT(*) FROM sys.key_constraints k WHERE k.parent_object_id = t.object_id AND k.type = 'UQ') AS unique_constraints,
       (SELECT COUNT(*) FROM sys.check_constraints k WHERE k.parent_object_id = t.object_id) AS check_constraints,
       (SELECT COUNT(*) FROM sys.default_constraints k WHERE k.parent_object_id = t.object_id) AS default_constraints,
       (SELECT COUNT(*) FROM sys.indexes i WHERE i.object_id = t.object_id AND i.is_unique = 1
            AND i.is_primary_key = 0 AND i.is_unique_constraint = 0) AS unique_indexes,
       (SELECT COUNT(*) FROM sys.extended_properties e WHERE e.class = 1 AND e.major_id = t.object_id
            AND e.minor_id = 0 AND e.name = 'MS_Description') AS table_descriptions,
       (SELECT COUNT(*) FROM sys.extended_properties e WHERE e.class = 1 AND e.major_id = t.object_id
            AND e.minor_id > 0 AND e.name = 'MS_Description') AS column_descriptions
  FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
 WHERE t.is_ms_shipped = 0
 ORDER BY s.name, t.name
"@
$rows = @($db.ExecuteWithResults($perTable).Tables[0].Rows)
if ($rows.Count -ne $tables.Count) {
    throw "catalog lists $($rows.Count) user tables but SMO scripted $($tables.Count)"
}

$keys = 'columns', 'primary_keys', 'foreign_keys', 'unique_constraints', 'check_constraints',
        'default_constraints', 'unique_indexes', 'table_descriptions', 'column_descriptions'
$counts = [ordered]@{ tables = $rows.Count }
foreach ($key in $keys) { $counts[$key] = [int](($rows | Measure-Object -Property $key -Sum).Sum) }
$perTableOut = foreach ($row in $rows) {
    $entry = [ordered]@{ name = "$($row.schema).$($row.table)" }
    foreach ($key in $keys) { $entry[$key] = [int]$row[$key] }
    $entry
}

$version = ($db.ExecuteWithResults("SELECT @@VERSION AS v").Tables[0].Rows[0].v -split "`n")[0].Trim()
$smoVersion = [Microsoft.SqlServer.Management.Smo.Server].Assembly.GetName().Version.ToString()
$today = (Get-Date).ToString('yyyy-MM-dd')
$header = @(
    '-- ModelBox DDL fixture: genuine tool output. Do not edit; regenerate it.'
    "-- source: $Source (MIT; see ../README.md)"
    "-- tool: SMO Scripter (the scripting engine behind SSMS), Microsoft.SqlServer.Smo $smoVersion, SqlServer module 22.4.5.1"
    "-- server: $version"
    '-- options: DriAll, Indexes, ExtendedProperties; no triggers, no collation, no headers; GO between statements'
    "-- image: $Image"
    "-- generated: $today by $Run"
    '-- end of provenance'
)

New-Item -ItemType Directory -Force -Path $Out | Out-Null
$body = ($statements | ForEach-Object { $_.TrimEnd() }) -join "`nGO`n"
$text = ($header -join "`n") + "`n" + $body + "`nGO`n"
[System.IO.File]::WriteAllText((Join-Path $Out 'adventureworks.sql'), $text, [System.Text.UTF8Encoding]::new($false))

$manifest = [ordered]@{
    fixture     = 'adventureworks.sql'
    dialect     = 'tsql'
    database    = $Database
    counts_from = 'catalog views (sys.tables, sys.columns, sys.key_constraints, sys.foreign_keys, sys.check_constraints, sys.default_constraints, sys.indexes, sys.extended_properties)'
    counts      = $counts
    tables      = @($perTableOut)
    catalog_query = ($perTable -replace '\s+', ' ').Trim()
    generated   = $today
    run         = $Run
}
[System.IO.File]::WriteAllText((Join-Path $Out 'adventureworks.manifest.json'),
    ($manifest | ConvertTo-Json -Depth 5) + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output "$Database : $($rows.Count) tables, counts $(($counts | ConvertTo-Json -Compress))"
