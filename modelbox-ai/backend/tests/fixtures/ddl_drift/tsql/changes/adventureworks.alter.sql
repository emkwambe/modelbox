-- Drift applied to AdventureWorks2022 after its fixture is exported (Sprint 8 Step 5).
-- ddl-fixtures.yml runs this against the real database, then scripts it again
-- with the same exporter into backend/tests/fixtures/ddl_drift/tsql.
-- Each statement is numbered; adventureworks.expected.json names the drift
-- each one makes, written from this script, not from ModelBox's output.
SET NOCOUNT ON;
GO
-- 1. A table removed.
DROP TABLE [dbo].[ErrorLog];
GO
-- 2. A NOT NULL column added with a default.
ALTER TABLE [Production].[Location] ADD [IsActive] [bit] NOT NULL CONSTRAINT [DF_Location_IsActive] DEFAULT ((1));
GO
-- 3. A type narrowed (the longest suffix in the data is three characters).
ALTER TABLE [Person].[Person] ALTER COLUMN [Suffix] [nvarchar](5) NULL;
GO
-- 4. A CHECK constraint removed.
ALTER TABLE [Production].[Product] DROP CONSTRAINT [CK_Product_Weight];
GO
-- 5. A column description changed.
EXEC sys.sp_updateextendedproperty @name=N'MS_Description', @value=N'A courtesy title, such as Mr. or Ms.', @level0type=N'SCHEMA', @level0name=N'Person', @level1type=N'TABLE', @level1name=N'Person', @level2type=N'COLUMN', @level2name=N'Title';
GO
-- 6. A column description removed.
EXEC sys.sp_dropextendedproperty @name=N'MS_Description', @level0type=N'SCHEMA', @level0name=N'Person', @level1type=N'TABLE', @level1name=N'Person', @level2type=N'COLUMN', @level2name=N'MiddleName';
GO
-- 7. A column renamed: reported as a removal and an addition, never as a rename.
EXEC sp_rename N'Sales.Store.Demographics', N'StoreDemographics', N'COLUMN';
GO
