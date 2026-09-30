-- Synthetic, written by hand for the computed-column export to PostgreSQL (see ../README.md). Not tool output.
-- The expressions are AdventureWorks' own, over columns of the same types.
SET ANSI_NULLS ON
GO
CREATE TABLE [dbo].[OrderLine](
	[OrderID] [int] IDENTITY(43659,1) NOT NULL,
	[Qty] [smallint] NOT NULL,
	[ScrappedQty] [smallint] NOT NULL,
	[UnitPrice] [money] NOT NULL,
	[UnitPriceDiscount] [money] NOT NULL,
	[SubTotal] [money] NOT NULL,
	[TaxAmt] [money] NOT NULL,
	[Freight] [money] NOT NULL,
	[ReceivedQty] [decimal](8, 2) NOT NULL,
	[RejectedQty] [decimal](8, 2) NOT NULL,
	[OrderNumber]  AS (isnull(N'SO'+CONVERT([nvarchar](23),[OrderID]),N'*** ERROR ***')),
	[LineTotal]  AS (isnull(([UnitPrice]*((1.0)-[UnitPriceDiscount]))*[Qty],(0.0))),
	[TotalDue]  AS (isnull(([SubTotal]+[TaxAmt])+[Freight],(0))) PERSISTED NOT NULL,
	[StockedQty]  AS (isnull([Qty]-[ScrappedQty],(0))),
	[AcceptedQty]  AS (isnull([ReceivedQty]-[RejectedQty],(0.00))),
	[PaddedID]  AS (isnull('AW'+[dbo].[ufnLeadingZeros]([OrderID]),'')),
 CONSTRAINT [PK_OrderLine_OrderID] PRIMARY KEY CLUSTERED
(
	[OrderID] ASC
) ON [PRIMARY]
) ON [PRIMARY]
GO
