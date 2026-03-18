variable "az_subscription_id" {
  type        = string
  description = "Azure Subscription ID"
}

variable "aad_admin_login_name" {
  type = string
}

variable "aad_admin_object_id" {
  type = string
}

variable "aad_admin_group_object_id" {
  type = string
}

variable "tenant_id" {
  type        = string
  description = "AAD tenant ID"
}

variable "location" {
  type    = string
  default = "West Europe"
}

variable "function_url" {
  type        = string
  description = "Function App endpoint URL"
}

variable "audience" {
  type = string
  description = "Function App audience"
}