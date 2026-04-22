## Entra Database User Setup

Use Azure Portal's SQL Database Query Editor, `sqlcmd`, or the Azure CLI to
create Entra-backed database users for:

- the App Service managed identity
- a local developer Entra account

This step is intentionally documented instead of embedded in application code.
Database principals and role membership are server-level administrative
operations and are not represented by the SQLAlchemy ORM models.

Recommended actions:

1. Create a user for the managed identity named `trendsApp`.
2. Grant the minimum roles required for the application.
3. Create a user for the developer Entra identity if local passwordless access is needed.
4. Verify the users and memberships from the Azure SQL side after creation.

Required role set in this project:

- `db_datareader`
- `db_datawriter`
- `db_ddladmin`

Notes:

- The managed identity user name must match the Azure user-assigned identity name.
- Run this only while connected as the Azure AD admin for the SQL Server.
- Keep principal management outside the ORM migration path.
