resource "azurerm_resource_group" "GB_Reporting_RG" {
  name     = "GB_Reporting_RG"
  location = "West Europe"
}

resource "azurerm_mssql_server" "gb-ads-sql-server" {
  name                                     = "gb-ads-sql-server"
  resource_group_name                      = azurerm_resource_group.GB_Reporting_RG.name
  location                                 = azurerm_resource_group.GB_Reporting_RG.location
  version                                  = "12.0"
  express_vulnerability_assessment_enabled = true

  azuread_administrator {
    azuread_authentication_only = true
    login_username              = var.aad_admin_login_name
    object_id                   = var.aad_admin_object_id
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_mssql_virtual_network_rule" "gb_ads_sql_allow_func_subnet_access" {
  name      = "allow-func-subnet-access"
  server_id = azurerm_mssql_server.gb-ads-sql-server.id
  subnet_id = azurerm_subnet.gb_func_integration_subnet_1.id
}

resource "azurerm_mssql_firewall_rule" "gb_ads_sql_allow_office_IP1" {
  name             = "allow-office-IP1"
  server_id        = azurerm_mssql_server.gb-ads-sql-server.id
  start_ip_address = "92.180.82.178"
  end_ip_address   = "92.180.82.178"
}
 
resource "azurerm_mssql_firewall_rule" "gb_ads_sql_allow_office_CF_IP" {
  name             = "allow_office_CF_IP"
  server_id        = azurerm_mssql_server.gb-ads-sql-server.id
  start_ip_address = "95.214.185.187"
  end_ip_address   = "95.214.185.187"
}

# Allow Azure Services to access SQL
resource "azurerm_mssql_firewall_rule" "gb-ads-sql-allow_azure_services" {
  name             = "AllowAllWindowsAzureIps"
  server_id        = azurerm_mssql_server.gb-ads-sql-server.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_database" "GB_Reporting_DB" {
  name                           = "GB_Reporting_DB"
  server_id                      = azurerm_mssql_server.gb-ads-sql-server.id
  collation                      = "SQL_Latin1_General_CP1_CI_AS"
  storage_account_type           = "Zone"
  maintenance_configuration_name = "SQL_WestEurope_DB_2"
  sku_name                       = "GP_Gen5_2" # Provisioned 2 vCores, Gen5

  short_term_retention_policy {
    retention_days = 35
  }

  long_term_retention_policy {
    weekly_retention  = "P2W" # 2 weeks
    monthly_retention = "P6M" # 6 months
    yearly_retention  = "P1Y" # 1 year
    week_of_year      = 1
  }

  lifecycle {
    prevent_destroy = true
  }
}
