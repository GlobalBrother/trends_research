# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "sql_server_fqdn" {
  description = "Fully qualified domain name of the SQL Server"
  value       = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "Name of the SQL database"
  value       = azurerm_mssql_database.trends.name
}

output "sql_database_id" {
  description = "Resource ID of the SQL database"
  value       = azurerm_mssql_database.trends.id
}

output "connection_string" {
  description = "ADO.NET connection string (password placeholder)"
  value       = "Server=tcp:${azurerm_mssql_server.main.fully_qualified_domain_name},1433;Database=${azurerm_mssql_database.trends.name};User ID=${var.sql_admin_user};Password=<your-password>;Encrypt=True;TrustServerCertificate=False;"
  sensitive   = true
}

output "pyodbc_connection_string" {
  description = "pyodbc connection string for Python (password placeholder)"
  value       = "Driver={ODBC Driver 18 for SQL Server};Server=tcp:${azurerm_mssql_server.main.fully_qualified_domain_name},1433;Database=${azurerm_mssql_database.trends.name};Uid=${var.sql_admin_user};Pwd=<your-password>;Encrypt=yes;TrustServerCertificate=no;"
  sensitive   = true
}

# --- Hosting outputs ---

output "app_service_url" {
  description = "The default URL of the App Service"
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_service_name" {
  description = "Name of the App Service"
  value       = azurerm_linux_web_app.main.name
}

output "acr_login_server" {
  description = "Login server URL for the Container Registry"
  value       = azurerm_container_registry.acr.login_server
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

output "managed_identity_client_id" {
  description = "Client ID of the Managed Identity"
  value       = azurerm_user_assigned_identity.app.client_id
}
