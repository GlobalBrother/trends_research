# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------
variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "West Europe"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "trends-research-rg"
}

variable "tags" {
  description = "Tags applied to every resource"
  type        = map(string)
  default = {
    project     = "trends-research"
    environment = "production"
  }
}

# ---------------------------------------------------------------------------
# SQL Server
# ---------------------------------------------------------------------------
variable "sql_server_name" {
  description = "Globally unique name for the Azure SQL Server"
  type        = string
  default     = "gb-ads-sql-server"
}

variable "sql_admin_user" {
  description = "SQL Server administrator login"
  type        = string
  default     = "CloudSAe0108f5f"
}

variable "sql_admin_password" {
  description = "SQL Server administrator password (ignored for existing servers)"
  type        = string
  sensitive   = true
  default     = "placeholder-ignored-by-lifecycle"
}

# ---------------------------------------------------------------------------
# Azure AD Admin (optional)
# ---------------------------------------------------------------------------
variable "aad_admin_login" {
  description = "Azure AD admin login name (leave empty to skip)"
  type        = string
  default     = ""
}

variable "aad_admin_object_id" {
  description = "Azure AD admin object ID (leave empty to skip)"
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# SQL Database
# ---------------------------------------------------------------------------
variable "sql_database_name" {
  description = "Name of the SQL database"
  type        = string
  default     = "Trends_DB"
}

variable "sql_sku_name" {
  description = "SKU name for the database (e.g. GP_S_Gen5_1 for serverless)"
  type        = string
  default     = "GP_S_Gen5_1"
}

variable "sql_max_size_gb" {
  description = "Maximum database size in GB"
  type        = number
  default     = 32
}

variable "sql_auto_pause_delay" {
  description = "Auto-pause delay in minutes (-1 to disable)"
  type        = number
  default     = -1
}

variable "sql_min_capacity" {
  description = "Minimum vCore capacity for serverless"
  type        = number
  default     = 0.5
}

# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------
variable "dev_ip_address" {
  description = "Developer public IP to allow through firewall (leave empty to skip)"
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Container Registry
# ---------------------------------------------------------------------------
variable "acr_name" {
  description = "Name of the Azure Container Registry (alphanumeric only, globally unique)"
  type        = string
  default     = "trendsresearchacr"
}

variable "docker_image_name" {
  description = "Docker image name (without registry prefix)"
  type        = string
  default     = "trends-research-app"
}

# ---------------------------------------------------------------------------
# Managed Identity
# ---------------------------------------------------------------------------
variable "managed_identity_name" {
  description = "Name of the User-Assigned Managed Identity"
  type        = string
  default     = "trendsApp"
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------
variable "key_vault_name" {
  description = "Name of the Azure Key Vault (globally unique, 3-24 chars)"
  type        = string
  default     = "kv-trends-app-prod"
}

variable "app_secrets" {
  description = "Additional secret names (hyphenated) to values for Key Vault. Merged with the explicit app secret variables below."
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "azure_sql_connectionstring" {
  description = "Optional full Azure SQL connection string stored as AZURE-SQL-CONNECTIONSTRING in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "azure_sql_server" {
  description = "Azure SQL server host stored as AZURE-SQL-SERVER in Key Vault"
  type        = string
  default     = ""
}

variable "azure_sql_database" {
  description = "Azure SQL database name stored as AZURE-SQL-DATABASE in Key Vault"
  type        = string
  default     = ""
}

variable "azure_sql_user" {
  description = "Optional SQL auth username stored as AZURE-SQL-USER in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "azure_sql_pass" {
  description = "Optional SQL auth password stored as AZURE-SQL-PASS in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ensembledata_token" {
  description = "EnsembleData API token stored as ENSEMBLEDATA-TOKEN in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "news_api_key" {
  description = "NewsAPI key stored as NEWS-API-KEY in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gethookedai_token" {
  description = "GetHookdAI token stored as GETHOOKEDAI-TOKEN in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "resend_api_key" {
  description = "Resend API key stored as RESEND-API-KEY in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

variable "resend_from_email" {
  description = "Resend sender address stored as RESEND-FROM-EMAIL in Key Vault"
  type        = string
  default     = ""
}

variable "test_account_email" {
  description = "Optional seeded test account email stored as TEST-ACCOUNT-EMAIL in Key Vault"
  type        = string
  default     = ""
}

variable "test_account_otp" {
  description = "Optional seeded test account OTP stored as TEST-ACCOUNT-OTP in Key Vault"
  type        = string
  sensitive   = true
  default     = ""
}

# ---------------------------------------------------------------------------
# App Service
# ---------------------------------------------------------------------------
variable "app_service_plan_name" {
  description = "Name of the App Service Plan"
  type        = string
  default     = "asp-trends-app"
}

variable "app_service_name" {
  description = "Name of the Azure Web App (must be globally unique)"
  type        = string
  default     = "trends-research-app"
}

variable "app_service_sku" {
  description = "SKU for the App Service Plan (F1, B1, B2, S1, P1v2, etc.)"
  type        = string
  default     = "B1"
}
