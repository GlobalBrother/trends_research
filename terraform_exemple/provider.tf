# Define the providers

terraform {
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 1.0"
    }
  }
}

# Provider for Azure resources
provider "azurerm" {
  features {}
  subscription_id = var.az_subscription_id
}

# Provider for Entra ID resources (App Registration, etc.)
provider "azuread" {
  tenant_id = var.tenant_id
}

provider "azapi" {}

