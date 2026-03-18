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
  description = "SQL Server administrator password"
  type        = string
  sensitive   = true
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
  default     = 60
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
