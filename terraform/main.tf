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
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

# Current client config (for Key Vault access policies)
data "azurerm_client_config" "current" {}

locals {
  required_app_secrets = merge(
    var.azure_sql_connectionstring != "" ? {
      "AZURE-SQL-CONNECTIONSTRING" = var.azure_sql_connectionstring
    } : {},
    var.azure_sql_server != "" ? {
      "AZURE-SQL-SERVER" = var.azure_sql_server
    } : {},
    var.azure_sql_database != "" ? {
      "AZURE-SQL-DATABASE" = var.azure_sql_database
    } : {},
    var.azure_sql_user != "" ? {
      "AZURE-SQL-USER" = var.azure_sql_user
    } : {},
    var.azure_sql_pass != "" ? {
      "AZURE-SQL-PASS" = var.azure_sql_pass
    } : {},
    var.ensembledata_token != "" ? {
      "ENSEMBLEDATA-TOKEN" = var.ensembledata_token
    } : {},
    var.news_api_key != "" ? {
      "NEWS-API-KEY" = var.news_api_key
    } : {},
    var.gethookedai_token != "" ? {
      "GETHOOKEDAI-TOKEN" = var.gethookedai_token
    } : {},
    var.resend_api_key != "" ? {
      "RESEND-API-KEY" = var.resend_api_key
    } : {},
    var.resend_from_email != "" ? {
      "RESEND-FROM-EMAIL" = var.resend_from_email
    } : {},
    var.test_account_email != "" ? {
      "TEST-ACCOUNT-EMAIL" = var.test_account_email
    } : {},
    var.test_account_otp != "" ? {
      "TEST-ACCOUNT-OTP" = var.test_account_otp
    } : {},
  )

  effective_app_secrets = merge(local.required_app_secrets, var.app_secrets)
}

# ---------------------------------------------------------------------------
# Resource Group (existing — managed externally, imported into state)
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags

  lifecycle {
    ignore_changes = [name, location]
  }
}

# ---------------------------------------------------------------------------
# SQL Server (existing — preserve AAD admin, identity, and password)
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

  # Preserve existing server config that we don't manage
  lifecycle {
    ignore_changes = [
      administrator_login_password,
      azuread_administrator,
      identity,
      tags,
    ]
  }
}

# ---------------------------------------------------------------------------
# SQL Database (existing — preserve current SKU and settings)
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

  # Preserve existing database config
  lifecycle {
    ignore_changes = [
      sku_name,
      max_size_gb,
      storage_account_type,
      tags,
    ]
  }
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
# Schema Deployment
# ---------------------------------------------------------------------------
# NOTE: Schema is managed by the app's startup migration (src/db/migrate.py).
# The azure_schema.sql provisioner has been removed — the ORM handles this
# automatically when the app starts via Base.metadata.create_all().

# ---------------------------------------------------------------------------
# Azure Container Registry
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# User-Assigned Managed Identity
# ---------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "app" {
  name                = var.managed_identity_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Azure Key Vault
# ---------------------------------------------------------------------------
resource "azurerm_key_vault" "main" {
  name                       = var.key_vault_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = var.tags

  # Access policy for the Terraform runner / your account
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "List", "Set", "Delete", "Recover", "Backup", "Restore", "Purge"]
  }

  # Access policy for the App's Managed Identity (read-only)
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = azurerm_user_assigned_identity.app.principal_id

    secret_permissions = ["Get", "List"]
  }
}

# Store secrets in Key Vault
# nonsensitive() is required because Terraform does not allow sensitive values
# as for_each keys. The secret *values* remain protected — only the map keys
# (e.g. "AZURE-SQL-SERVER") are exposed as resource instance addresses.
resource "azurerm_key_vault_secret" "app_secrets" {
  for_each     = nonsensitive(local.effective_app_secrets)
  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_key_vault.main]
}

# ---------------------------------------------------------------------------
# App Service Plan (Linux)
# ---------------------------------------------------------------------------
resource "azurerm_service_plan" "main" {
  name                = var.app_service_plan_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# App Service (Web App for Containers)
# ---------------------------------------------------------------------------
resource "azurerm_linux_web_app" "main" {
  name                = var.app_service_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  site_config {
    always_on = var.app_service_sku != "F1"

    application_stack {
      docker_image_name        = "${var.docker_image_name}:latest"
      docker_registry_url      = "https://${azurerm_container_registry.acr.login_server}"
      docker_registry_username = azurerm_container_registry.acr.admin_username
      docker_registry_password = azurerm_container_registry.acr.admin_password
    }

    health_check_path = "/health"
  }

  app_settings = {
    # Key Vault — the app reads all secrets from here at startup
    "KEY_VAULT_NAME"             = azurerm_key_vault.main.name
    "MANAGED_IDENTITY_CLIENT_ID" = azurerm_user_assigned_identity.app.client_id

    # App configuration
    "WEBSITES_PORT"                       = "8000"
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"

    # Docker registry
    "DOCKER_REGISTRY_SERVER_URL"      = "https://${azurerm_container_registry.acr.login_server}"
    "DOCKER_REGISTRY_SERVER_USERNAME" = azurerm_container_registry.acr.admin_username
    "DOCKER_REGISTRY_SERVER_PASSWORD" = azurerm_container_registry.acr.admin_password
  }

  logs {
    application_logs {
      file_system_level = "Information"
    }
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Azure Communication Services (Email)
# ---------------------------------------------------------------------------
resource "azurerm_communication_service" "main" {
  name                = "acs-trends-research"
  resource_group_name = azurerm_resource_group.main.name
  data_location       = "Europe"
  tags                = var.tags
}

resource "azurerm_email_communication_service" "main" {
  name                = "acs-email-trends-research"
  resource_group_name = azurerm_resource_group.main.name
  data_location       = "Europe"
  tags                = var.tags
}

# Azure-managed domain — no DNS verification needed
resource "azurerm_email_communication_service_domain" "managed" {
  name              = "AzureManagedDomain"
  email_service_id  = azurerm_email_communication_service.main.id
  domain_management = "AzureManaged"
}

# Link the email domain to the Communication Service
resource "azurerm_communication_service_email_domain_association" "main" {
  communication_service_id = azurerm_communication_service.main.id
  email_service_domain_id  = azurerm_email_communication_service_domain.managed.id
}

# Store ACS connection string in Key Vault
resource "azurerm_key_vault_secret" "acs_connection_string" {
  name         = "ACS-CONNECTION-STRING"
  value        = azurerm_communication_service.main.primary_connection_string
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_key_vault.main]
}

# Store ACS sender address in Key Vault
resource "azurerm_key_vault_secret" "acs_sender_address" {
  name         = "ACS-SENDER-ADDRESS"
  value        = "DoNotReply@${azurerm_email_communication_service_domain.managed.from_sender_domain}"
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_key_vault.main]
}

# NOTE: App Service → SQL Server connectivity is already covered by the
# "AllowAzureServices" firewall rule (0.0.0.0–0.0.0.0) defined above,
# which permits all Azure-internal traffic. No per-IP rules are needed.
