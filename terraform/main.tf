terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  backend "azurerm" {
    resource_group_name  = "tfstate-rg"
    storage_account_name = "tfstatetrends"
    container_name       = "tfstate"
    key                  = "trends-research.tfstate"
  }
}

provider "azurerm" {
  features {}
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# ---------------------------------------------------------------------------
# SQL Server
# ---------------------------------------------------------------------------
resource "azurerm_mssql_server" "main" {
  name                         = var.sql_server_name
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_user
  administrator_login_password = var.sql_admin_password
  minimum_tls_version          = "1.2"
  tags                         = var.tags

  dynamic "azuread_administrator" {
    for_each = var.aad_admin_object_id != "" ? [1] : []
    content {
      login_username = var.aad_admin_login
      object_id      = var.aad_admin_object_id
    }
  }
}

# ---------------------------------------------------------------------------
# SQL Database
# ---------------------------------------------------------------------------
resource "azurerm_mssql_database" "trends" {
  name      = var.sql_database_name
  server_id = azurerm_mssql_server.main.id

  sku_name                    = var.sql_sku_name
  max_size_gb                 = var.sql_max_size_gb
  zone_redundant              = false
  auto_pause_delay_in_minutes = var.sql_auto_pause_delay
  min_capacity                = var.sql_min_capacity

  short_term_retention_policy {
    retention_days           = 7
    backup_interval_in_hours = 12
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Firewall Rules
# ---------------------------------------------------------------------------

# Allow Azure services (required for App Service / Container Apps)
resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Optional: allow a specific client IP for development
resource "azurerm_mssql_firewall_rule" "allow_dev" {
  count            = var.dev_ip_address != "" ? 1 : 0
  name             = "AllowDevMachine"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = var.dev_ip_address
  end_ip_address   = var.dev_ip_address
}

# ---------------------------------------------------------------------------
# Schema Deployment (runs azure_schema.sql after DB creation)
# ---------------------------------------------------------------------------
resource "terraform_data" "schema_deploy" {
  depends_on = [azurerm_mssql_database.trends]

  triggers_replace = [
    filesha256("${path.module}/../src/db/azure_schema.sql")
  ]

  provisioner "local-exec" {
    command = <<-EOT
      sqlcmd -S ${azurerm_mssql_server.main.fully_qualified_domain_name} ^
             -d ${azurerm_mssql_database.trends.name} ^
             -U ${var.sql_admin_user} ^
             -P "${var.sql_admin_password}" ^
             -i "${path.module}/../src/db/azure_schema.sql" ^
             -N -C
    EOT
  }
}
