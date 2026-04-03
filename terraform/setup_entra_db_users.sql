-- ============================================================================
-- Setup Entra ID (Azure AD) database users for Trends Research App
-- ============================================================================
-- Run this script in Azure Portal > SQL Database > Query Editor
-- You MUST be logged in as the Azure AD admin of the SQL Server.
--
-- This script creates two database users:
--   1. The Managed Identity (for the App Service in production)
--   2. Your personal Entra ID account (for local development)
-- ============================================================================

-- 1. Create the Managed Identity user (used by App Service)
-- The name MUST match the User-Assigned Managed Identity name in Azure.
CREATE USER [trendsApp] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [trendsApp];
ALTER ROLE db_datawriter ADD MEMBER [trendsApp];
ALTER ROLE db_ddladmin ADD MEMBER [trendsApp];
GO

-- 2. Create your personal Entra ID user (for local dev via az login)
-- Replace with your actual Azure AD email if different.
CREATE USER [marian.craciun@globalbrother.com] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [marian.craciun@globalbrother.com];
ALTER ROLE db_datawriter ADD MEMBER [marian.craciun@globalbrother.com];
ALTER ROLE db_ddladmin ADD MEMBER [marian.craciun@globalbrother.com];
GO

-- ============================================================================
-- Verify the users were created:
-- SELECT name, type_desc FROM sys.database_principals WHERE type IN ('E','X');
-- ============================================================================
