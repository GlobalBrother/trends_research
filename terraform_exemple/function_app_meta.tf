# App Service Plan + Storage Account for Function App
resource "azurerm_storage_account" "gb_reporting_storage" {
  name                          = "gbreportingstorage"
  resource_group_name           = azurerm_resource_group.GB_Reporting_RG.name
  location                      = azurerm_resource_group.GB_Reporting_RG.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }

  network_rules {
  default_action = "Deny"
  bypass         = [
    "AzureServices"
  ]
 
  virtual_network_subnet_ids = [
    azurerm_subnet.gb_func_integration_subnet_1.id
  ]
  }

}

resource "azurerm_service_plan" "gb_ads_reporting_flex_plan" {
  name                = "gb-ads-reporting-flex-plan"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name
  os_type             = "Linux"
  sku_name            = "FC1"
}

# Azure AD Application for Function App Authentication
# This application is used for authenticating the Function App with Azure AD.
resource "azuread_application" "gb_metaads_flex_function_auth_app" {
  display_name = "gb-metaads-function"
  # Identifier URIs are used to uniquely identify the application in Azure AD. added after the app was created
  identifier_uris = ["api://a12db87f-e1e0-4d38-a70f-fe363aedd951", ]
  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      admin_consent_description  = "Allow the application to access gb-metaads-function on behalf of the signed-in user."
      admin_consent_display_name = "Access gb-metaads-function"
      id                         = "91c4fba1-a899-43ea-8557-879695d98a5f"
      enabled                    = true
      type                       = "User"
      user_consent_description   = "Allow the application to access gb-metaads-function on your behalf."
      user_consent_display_name  = "Access gb-metaads-function"
      value                      = "user_impersonation"
    }
  }
  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph
    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d" # User.Read.All
      type = "Scope"
    }
  }
  web {
    homepage_url  = "https://gb-metaads-function.azurewebsites.net"
    redirect_uris = ["https://gb-metaads-flex-function.azurewebsites.net/.auth/login/aad/callback",]
    implicit_grant {
      access_token_issuance_enabled = false
      id_token_issuance_enabled     = true
    }
  }
}

# Azure AD Service Principal/enterprise app for Function App Authentication
resource "azuread_service_principal" "gb_metaads_flex_function_auth_sp" {
  client_id = azuread_application.gb_metaads_flex_function_auth_app.client_id
}
# output "sp_names" {
#   value = azuread_service_principal.gb_metaads_flex_function_auth_sp.client_id
# }

resource "azurerm_function_app_flex_consumption" "gb_metaads_flex_function" {
  name                        = "gb-metaads-flex-function"
  location                    = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name         = azurerm_resource_group.GB_Reporting_RG.name
  service_plan_id             = azurerm_service_plan.gb_ads_reporting_flex_plan.id
  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.gb_reporting_storage.primary_blob_endpoint}${azurerm_storage_container.gb_metaads_flex_function_container.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.gb_reporting_storage.primary_access_key
 
  runtime_name           = "python"
  runtime_version        = "3.12"
  maximum_instance_count = 50
  instance_memory_in_mb  = 2048
 
  virtual_network_subnet_id = azurerm_subnet.gb_func_integration_subnet_1.id
  https_only                = true
 
  identity {
    type = "SystemAssigned"
  }
 
  site_config {
    application_insights_connection_string = azurerm_application_insights.gb_metaads_app_insights.connection_string
    minimum_tls_version                    = "1.2"
    http2_enabled                          = true
  }
 
  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "Return401"
    default_provider       = "aad"
    require_https          = true
 
    login {
      token_store_enabled = true
    }
 
    active_directory_v2 {
      client_id                  = azuread_application.gb_metaads_flex_function_auth_app.client_id
      tenant_auth_endpoint       = "https://sts.windows.net/${var.tenant_id}/v2.0"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
      allowed_audiences          = azuread_application.gb_metaads_flex_function_auth_app.identifier_uris
      allowed_identities = [
        azuread_service_principal.gb_metaads_flex_function_auth_sp.client_id,
 
        # Logic Apps – Structure
        azurerm_logic_app_workflow.meta_scheduler_business_all.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_accounts_daily.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_campaigns_daily.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_adsets_daily.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_ads_daily.identity[0].principal_id,
        # Logic Apps – Insights Hourly
        azurerm_logic_app_workflow.meta_scheduler_account_insights_hourly.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_campaign_insights_hourly.identity[0].principal_id,
        # Logic Apps – Insights Backfill
        azurerm_logic_app_workflow.meta_scheduler_account_insights_backfill.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_campaign_insights_backfill.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_campaign_insights_backfill_yesterday.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_adset_insights_backfill.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_ad_insights_backfill.identity[0].principal_id,
        # Logic Apps – Generate Afilliate Reports
        azurerm_logic_app_workflow.meta_scheduler_generate_affiliate_report_hourly.identity[0].principal_id,
        azurerm_logic_app_workflow.meta_scheduler_generate_affiliate_report_backfill.identity[0].principal_id,
        # Logic Apps – Meta Alerts
        azurerm_logic_app_workflow.budget_alert.identity[0].principal_id

      ]
    }
  }
 
  sticky_settings {
    app_setting_names = ["MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"]
  }
 
  app_settings = {
    AZURE_SQL_SERVER                         = azurerm_mssql_server.gb-ads-sql-server.fully_qualified_domain_name
    AZURE_SQL_DB                             = azurerm_mssql_database.GB_Reporting_DB.name
    AZURE_SQL_DB_TEST                        = "test_db_ads_data"
    META_KEY_VAULT_URL                       = azurerm_key_vault.gb-ads-reporting-kv.vault_uri
    AFFILIATES_KEY_VAULT_URL                 = azurerm_key_vault.gb-ads-affiliates-kv.vault_uri
    AzureWebJobsStorage                      = azurerm_storage_account.gb_reporting_storage.primary_connection_string
    remoteBuild                              = true
    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azurerm_key_vault_secret.func_ms_auth_secret.value
    WEBSITE_AUTH_AAD_ALLOWED_TENANTS         = var.tenant_id
    TEST_DB                                  = "False"
    DST_TABLE                                = "facebook_ads"
    COLUMNS                                  = "id,report_date,account_name,product_id,currency,ammount_spent,purchases"
    BATCH_SIZE                               = "5000"
    SSH_HOST                                 = "34.88.0.110"
    SSH_PORT                                 = 22
    SSH_USER                                 = "Tunnel-User"
    SSH_KEY_PATH                             = "Private-Key"
    MARIADB_USER                             = "User"
    MARIADB_PASS                             = "Password"
    MARIADB_NAME                             = "Database"
    GLOBALBROTHER_ID                         = 3483466598346284
    TLK_ID                                   = 913022432822559
    BOR_ID                                   = 137042760602297
    LOG_PATH                                 = "." 

  }
 
  tags = {
    "hidden-link: /app-insights-resource-id" = azurerm_application_insights.gb_metaads_app_insights.id
  }
 
  lifecycle {
    ignore_changes = [
      tags["hidden-link: /app-insights-resource-id"],
    ]
  }
  depends_on = [
    azurerm_resource_provider_registration.microsoft_app
  ]
}

resource "azurerm_resource_provider_registration" "microsoft_app" {

  name = "Microsoft.App"

}
resource "azurerm_application_insights" "gb_metaads_app_insights" {
  name                = "gb_metaads_app_insights"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name
  application_type    = "web"
  workspace_id        = "/subscriptions/254809ba-01b2-4e38-9d36-274f2e001653/resourceGroups/ai_gb_metaads_app_insights_298ed5cb-704e-4e75-bff4-8c3d5c74ebfb_managed/providers/Microsoft.OperationalInsights/workspaces/managed-gb-metaads-app-insights-ws"
}

resource "azurerm_role_assignment" "metaads_function_storage_access" {
  scope                = azurerm_storage_account.gb_reporting_storage.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_function_app_flex_consumption.gb_metaads_flex_function.identity[0].principal_id
}

