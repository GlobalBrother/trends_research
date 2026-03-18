# ACS Resource
resource "azurerm_communication_service" "gb_acs_alerts" {
  name                = "gb-acs-alerts"
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name
  data_location       = "Europe"
}

resource "azurerm_email_communication_service" "gb_email_alerts" {
  name                = "testalertemail"
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name
  data_location       = "Europe"
}

#create the email domain that will be used for sending the email alerts
resource "azurerm_email_communication_service_domain" "gb_email_alerts_source_domain" {
  name              = "AzureManagedDomain"
  email_service_id  = azurerm_email_communication_service.gb_email_alerts.id
  domain_management = "AzureManaged"
}

resource "azurerm_communication_service_email_domain_association" "gb_email_alerts_association" {
  communication_service_id = azurerm_communication_service.gb_acs_alerts.id
  email_service_domain_id  = azurerm_email_communication_service_domain.gb_email_alerts_source_domain.id
}
