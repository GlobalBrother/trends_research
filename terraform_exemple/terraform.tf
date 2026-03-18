terraform {
  required_version = ">= 1.13.4"
  backend "azurerm" {
    resource_group_name  = "gb_tfstate_rg"
    storage_account_name = "gbtfstatesa"
    container_name       = "gb-reporting-tf-state"
    key                  = "gb-reporting/prod/terraform.tfstate"
  }
}

resource "azurerm_resource_group" "gb_tfstate_rg" {
  name     = "gb_tfstate_rg"
  location = var.location
}

resource "azurerm_storage_account" "gb_tfstate_sa" {
  name                     = "gbtfstatesa"
  resource_group_name      = azurerm_resource_group.gb_tfstate_rg.name
  location                 = azurerm_resource_group.gb_tfstate_rg.location
  account_tier             = "Standard"
  account_replication_type = "ZRS"
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = true
  shared_access_key_enabled       = true
  public_network_access_enabled   = true

  # Restrict access to office IPs
  network_rules {
    default_action = "Deny"
    ip_rules       = ["92.180.82.178", "80.76.57.185", "95.214.185.187"]
    bypass         = ["AzureServices"]
  }

  blob_properties {
    versioning_enabled  = true
    change_feed_enabled = true

    delete_retention_policy {
      days = 90
    }

    container_delete_retention_policy {
      days = 14
    }
  }

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Purpose     = "Store Terraform State Files"
    Environment = "Prod"
  }
}

resource "azurerm_storage_container" "gb_reporting_tf_state" {
  name                  = "gb-reporting-tf-state"
  storage_account_id    = azurerm_storage_account.gb_tfstate_sa.id
  container_access_type = "private"
}

# flex consumption requires a blob container to store app packages
resource "azurerm_storage_container" "gb_metaads_flex_function_container" {
  name                  = "gb-metaads-flex-function-container"
  storage_account_id    = azurerm_storage_account.gb_reporting_storage.id
  container_access_type = "private"
}

resource "azurerm_virtual_network" "gb_func_vnet" {
  name                = "gb-func-vnet"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name
  address_space       = ["10.9.0.0/16"]
}
 
resource "azurerm_subnet" "gb_func_integration_subnet_1" {
  name                 = "gb-func-integration-subnet-1"
  resource_group_name  = azurerm_resource_group.GB_Reporting_RG.name
  virtual_network_name = azurerm_virtual_network.gb_func_vnet.name
  address_prefixes     = ["10.9.1.0/24"]
 
  # Service endpoints for Key Vault
  service_endpoints = [
    "Microsoft.KeyVault",
    "Microsoft.Sql",
    "Microsoft.Storage"
  ]
 
  # Required for Flex Function App VNet integration
  delegation {
    name = "flex-private-subnet-delegation"
 
    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/action",
      ]
    }
  }
}