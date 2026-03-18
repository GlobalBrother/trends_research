# Key Vault
resource "azurerm_key_vault" "gb-ads-affiliates-kv" {
  name                          = "gb-ads-affiliates-kv"
  resource_group_name           = azurerm_resource_group.GB_Reporting_RG.name
  location                      = azurerm_resource_group.GB_Reporting_RG.location
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  purge_protection_enabled      = true
  public_network_access_enabled = true

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules = [
      "92.180.82.178",
      "95.214.185.187",
      "34.88.0.110"
    ]
    virtual_network_subnet_ids = [
        azurerm_subnet.gb_func_integration_subnet_1.id
    ]
  }
}

# Key Vault Secrets (values updated manually after deploy)
resource "azurerm_key_vault_secret" "affiliates-user" {
  name         = "Affiliates-User"
  value        = "PLACEHOLDER_USER"
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id

  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "affiliates-password" {
  name         = "Affiliates-Password"
  value        = "PLACEHOLDER_PASSWORD"
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id
  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "affiliates-private-key" {
  name         = "Affiliates-Private-Key"
  value        = "PLACEHOLDER_PRIVATE-KEY"
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id

  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "affiliates-tunnel-user" {
  name         = "Affiliates-Tunnel-User"
  value        = "PLACEHOLDER_TUNNEL_USER"
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id

  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "affiliates-database" {
  name         = "Affiliates-Database"
  value        = "PLACEHOLDER_DATABASE"
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id

  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

# Give Azure Function App access to Key Vault
resource "azurerm_key_vault_access_policy" "metaads_flex_function_affiliates_kv_access" {
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id
  tenant_id    = var.tenant_id
  object_id    = azurerm_function_app_flex_consumption.gb_metaads_flex_function.identity[0].principal_id
 
  secret_permissions = ["Get", "List"]
}
 
# Assign 'Key Vault Secrets User' role to the Function App
resource "azurerm_role_assignment" "metaads_flex_function_affiliates_kv_role" {
  scope                = azurerm_key_vault.gb-ads-affiliates-kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_function_app_flex_consumption.gb_metaads_flex_function.identity[0].principal_id
}

# Give Admin Users access to Key Vault
resource "azurerm_key_vault_access_policy" "gb-ads-affiliates-kv_admin_access" {
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id
  tenant_id    = var.tenant_id
  object_id    = var.aad_admin_object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover", "Backup", "Restore"]
  key_permissions    = ["Get", "List", "Create", "Delete", "Recover", "Backup", "Restore", "Import", "Update"]
}

resource "azurerm_key_vault_access_policy" "gb-ads-affiliates-kv_admin_access_group" {
  key_vault_id = azurerm_key_vault.gb-ads-affiliates-kv.id
  tenant_id    = var.tenant_id
  object_id    = var.aad_admin_group_object_id

  secret_permissions = ["Get", "List", "Set", "Delete"]
  key_permissions    = ["Get", "List", "Create", "Delete", "Update"]
}

resource "azurerm_key_vault" "gb-ads-reporting-kv" {
  name                          = "gb-ads-reporting-kv"
  resource_group_name           = azurerm_resource_group.GB_Reporting_RG.name
  location                      = azurerm_resource_group.GB_Reporting_RG.location
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  purge_protection_enabled      = true
  public_network_access_enabled = true

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules = [
      "92.180.82.178",
      "95.214.185.187"
    ]
    virtual_network_subnet_ids = [
        azurerm_subnet.gb_func_integration_subnet_1.id
    ]
  }
}

# Key Vault Secrets (values updated manually after deploy)
resource "azurerm_key_vault_secret" "meta-globalbrother-business-act-token" {
  name         = "GlobalBrother-token"
  value        = "PLACEHOLDER_TOKEN_1"
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id

  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "meta-bor-business-act-token" {
  name         = "BOR-token"
  value        = "PLACEHOLDER_TOKEN_2"
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id
  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "meta-tlk-business-act-token" {
  name         = "TLK-token"
  value        = "PLACEHOLDER_TOKEN_3"
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id
  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_secret" "func_ms_auth_secret" {
  name         = "func-ms-auth-secret"
  value        = "PLACEHOLDER_TOKEN"
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id
  lifecycle {
    ignore_changes = [
      value
    ]
  }
}

resource "azurerm_key_vault_access_policy" "metaads_flex_function_kv_access" {
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id
  tenant_id    = var.tenant_id
  object_id    = azurerm_function_app_flex_consumption.gb_metaads_flex_function.identity[0].principal_id
 
  secret_permissions = ["Get", "List"]
}
 
# Assign 'Key Vault Secrets User' role to the Function App
resource "azurerm_role_assignment" "metaads_flex_function_kv_role" {
  scope                = azurerm_key_vault.gb-ads-reporting-kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_function_app_flex_consumption.gb_metaads_flex_function.identity[0].principal_id
}

# Give Admin Users access to Key Vault
resource "azurerm_key_vault_access_policy" "gb-ads-reporting-kv_admin_access" {
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id
  tenant_id    = var.tenant_id
  object_id    = var.aad_admin_object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover", "Backup", "Restore"]
  key_permissions    = ["Get", "List", "Create", "Delete", "Recover", "Backup", "Restore", "Import", "Update"]
}

resource "azurerm_key_vault_access_policy" "gb-ads-reporting-kv_admin_access_group" {
  key_vault_id = azurerm_key_vault.gb-ads-reporting-kv.id
  tenant_id    = var.tenant_id
  object_id    = var.aad_admin_group_object_id

  secret_permissions = ["Get", "List", "Set", "Delete"]
  key_permissions    = ["Get", "List", "Create", "Delete", "Update"]
}