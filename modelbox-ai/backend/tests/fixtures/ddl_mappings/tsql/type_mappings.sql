-- Synthetic, written by hand for the type mappings to PostgreSQL (see ../README.md). Not tool output.
SET ANSI_NULLS ON
GO
CREATE TABLE [dbo].[Ledger](
	[LedgerID] [int] IDENTITY(100000,5) NOT NULL,
	[Amount] [money] NOT NULL,
	[Fee] [smallmoney] NULL,
	[IsActive] [bit] NOT NULL,
	[IsVoid] [bit] NOT NULL,
 CONSTRAINT [PK_Ledger_LedgerID] PRIMARY KEY CLUSTERED
(
	[LedgerID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE TABLE [dbo].[Batch](
	[BatchID] [bigint] IDENTITY(1,1) NOT NULL,
	[Node] [hierarchyid] NULL,
	[Location] [geography] NULL,
 CONSTRAINT [PK_Batch_BatchID] PRIMARY KEY CLUSTERED
(
	[BatchID] ASC
) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Ledger] ADD  CONSTRAINT [DF_Ledger_IsActive]  DEFAULT ((1)) FOR [IsActive]
GO
ALTER TABLE [dbo].[Ledger] ADD  CONSTRAINT [DF_Ledger_IsVoid]  DEFAULT ((0)) FOR [IsVoid]
GO
ALTER TABLE [dbo].[Ledger]  WITH CHECK ADD  CONSTRAINT [CK_Ledger_Amount] CHECK  (([Amount]>=(0.00)))
GO
ALTER TABLE [dbo].[Ledger] CHECK CONSTRAINT [CK_Ledger_Amount]
GO
ALTER TABLE [dbo].[Ledger]  WITH CHECK ADD  CONSTRAINT [CK_Ledger_VoidIsInactive] CHECK  (([IsVoid]=(0) OR [IsActive]=(0)))
GO
ALTER TABLE [dbo].[Ledger] CHECK CONSTRAINT [CK_Ledger_VoidIsInactive]
GO
