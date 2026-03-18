# Logic App to trigger the Function App job - Business All (Monthly on 1st at 00:00)
resource "azurerm_logic_app_workflow" "meta_scheduler_business_all" {
  name                = "01_meta_scheduler_business_all"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_business_all" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_business_all.id
  frequency = "Month"
  interval = 1

  name          = "Business_All"
  pipeline_name = "business_all"

  include_hours = [0]
  minute        = 0

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_business_all" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_business_all.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Accounts Daily at 08:00
resource "azurerm_logic_app_workflow" "meta_scheduler_accounts_daily" {
  name                = "02_meta_scheduler_accounts_daily"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_accounts_daily" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_accounts_daily.id
  frequency    = "Day"
  interval     = 1

  name          = "Accounts_Daily"
  pipeline_name = "accounts"

  include_hours = [8]
  minute        = 0

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_accounts_daily" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_accounts_daily.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Campaigns Daily at 08:30 12:30 16:30
resource "azurerm_logic_app_workflow" "meta_scheduler_campaigns_daily" {
  name                = "03_meta_scheduler_campaigns_daily"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_campaigns_daily" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_campaigns_daily.id
  frequency    = "Day"
  interval     = 1

  name          = "Campaigns"
  pipeline_name = "campaigns"

  include_hours = [8,12,16]
  minute        = 30

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_campaigns_daily" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_campaigns_daily.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - AdSets Daily at 18:30
resource "azurerm_logic_app_workflow" "meta_scheduler_adsets_daily" {
  name                = "04_meta_scheduler_adsets_daily"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_adsets_daily" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_adsets_daily.id
  frequency    = "Day"
  interval     = 1

  name          = "AdSets"
  pipeline_name = "adsets"

  include_hours = [18]
  minute        = 30

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_adsets_daily" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_adsets_daily.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Ads Daily at 20:00
resource "azurerm_logic_app_workflow" "meta_scheduler_ads_daily" {
  name                = "05_meta_scheduler_ads_daily"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_ads_daily" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_ads_daily.id
  frequency    = "Day"
  interval     = 1

  name          = "Ads"
  pipeline_name = "ads"

  include_hours = [20]
  minute        = 00

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_ads_daily" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_ads_daily.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Account Insights Hourly at 9:00 - 22:00
resource "azurerm_logic_app_workflow" "meta_scheduler_account_insights_hourly" {
  name                = "06_meta_scheduler_account_insights_hourly"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_account_insights_hourly" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_account_insights_hourly.id
  frequency    = "Day"
  interval     = 1

  name          = "Account Insights"
  pipeline_name = "account_insights"

  include_hours = [9,10,11,12,13,14,15,16,17,18,19,20,21,22,23]
  minute        = 00

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_account_insights_hourly" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_account_insights_hourly.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Campaign Insights Hourly at 9:00 - 22:00
resource "azurerm_logic_app_workflow" "meta_scheduler_campaign_insights_hourly" {
  name                = "07_meta_scheduler_campaign_insights_hourly"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_campaign_insights_hourly" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_campaign_insights_hourly.id
  frequency    = "Day"
  interval     = 1

  name          = "Campaign Insights"
  pipeline_name = "campaign_insights"

  include_hours = [9,10,11,12,13,14,15,16,17,18,19,20,21,22,23]
  minute        = 5

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_campaign_insights_hourly" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_campaign_insights_hourly.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Generate Affiliate Report
resource "azurerm_logic_app_workflow" "meta_scheduler_generate_affiliate_report_hourly" {
  name                = "08_meta_scheduler_generate_affiliate_report_hourly"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_generate_affiliate_report_hourly" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_generate_affiliate_report_hourly.id
  frequency    = "Day"
  interval     = 1

  name          = "Generate Affiliate Report"
  pipeline_name = "affiliate_report"

  include_hours = [9,10,11,12,13,14,15,16,17,18,19,20,21,22,23]
  minute        = 30

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_generate_affiliate_report_hourly" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_generate_affiliate_report_hourly.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Account Insights Daily at 00:00
resource "azurerm_logic_app_workflow" "meta_scheduler_account_insights_backfill" {
  name                = "09_meta_scheduler_account_insights_backfill"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_account_insights_backfill" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_account_insights_backfill.id
  frequency    = "Day"
  interval     = 1

  name          = "Account Insights"
  
  is_backfill = true
  pipeline_name = "account_insights"
  backfill_days_since = 7
  backfill_days_until = 0

  include_hours = [00]
  minute        = 00

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_account_insights_backfill" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_account_insights_backfill.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Campaign Insights Daily at 00:15
resource "azurerm_logic_app_workflow" "meta_scheduler_campaign_insights_backfill" {
  name                = "10_meta_scheduler_campaign_insights_backfill"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_campaign_insights_backfill" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_campaign_insights_backfill.id
  frequency    = "Day"
  interval     = 1

  name          = "Campaign Insights"
  
  is_backfill = true
  pipeline_name = "campaign_insights"
  backfill_days_since = 7
  backfill_days_until = 0

  include_hours = [00]
  minute        = 15

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_campaign_insights_backfill" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_campaign_insights_backfill.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Campaign Insights Daily at 08:30 12:30 16:30
resource "azurerm_logic_app_workflow" "meta_scheduler_campaign_insights_backfill_yesterday" {
  name                = "11_meta_scheduler_campaign_insights_backfill_yesterday"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}
  

module "scheduler_campaign_insights_backfill_yesterday" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_campaign_insights_backfill_yesterday.id
  frequency    = "Day"
  interval     = 1

  name          = "Campaign Insights"
  
  is_backfill = true
  pipeline_name = "campaign_insights"
  backfill_days_since = 1
  backfill_days_until = 0

  include_hours = [8,12,16]
  minute        = 40

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_campaign_insights_backfill_yesterday" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_campaign_insights_backfill_yesterday.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Generate Affiliate Report Backfill Daily at 02:45
resource "azurerm_logic_app_workflow" "meta_scheduler_generate_affiliate_report_backfill" {
  name                = "12_meta_scheduler_generate_affiliate_report_backfill"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_generate_affiliate_report_backfill" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_generate_affiliate_report_backfill.id
  frequency    = "Day"
  interval     = 1

  name          = "Generate Affiliate Report Backfill"
  
  is_backfill = true
  pipeline_name = "affiliate_report"
  backfill_days_since = 7
  backfill_days_until = 0

  include_hours = [02, 08, 12, 16]
  minute        = 58

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_generate_affiliate_report_backfill" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_generate_affiliate_report_backfill.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - AdSet Insights Daily at 03:00
resource "azurerm_logic_app_workflow" "meta_scheduler_adset_insights_backfill" {
  name                = "13_meta_scheduler_adset_insights_backfill"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_adset_insights_backfill" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_adset_insights_backfill.id
  frequency    = "Day"
  interval     = 1

  name          = "AdSet Insights"
  
  is_backfill = true
  pipeline_name = "adset_insights"
  backfill_days_since = 8
  backfill_days_until = 7

  include_hours = [3]
  minute        = 00

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_adset_insights_backfill" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_adset_insights_backfill.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# Logic App to trigger the Function App job - Ad Insights Daily at 4:00
resource "azurerm_logic_app_workflow" "meta_scheduler_ad_insights_backfill" {
  name                = "14_meta_scheduler_ad_insights_backfill"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity { type = "SystemAssigned" }

  parameters = {
    "$connections" = jsonencode({})
  }

  workflow_parameters = {
    "$connections" = jsonencode({
      defaultValue = {}
      type         = "Object"
    })
  }
}

module "scheduler_ad_insights_backfill" {
  source       = "./modules/logicapp_scheduler"
  logic_app_id = azurerm_logic_app_workflow.meta_scheduler_ad_insights_backfill.id
  frequency    = "Day"
  interval     = 1

  name          = "Ad Insights"
  
  is_backfill = true
  pipeline_name = "ad_insights"
  backfill_days_since = 8
  backfill_days_until = 7

  include_hours = [4]
  minute        = 00

  function_url = var.function_url
  audience     = var.audience

  create_init_variables = true
}

module "rbac_ad_insights_backfill" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.meta_scheduler_ad_insights_backfill.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}

# --------------------------------------
# Logic App to trigger Ads Spend Alerts
# I had to add the sql connection manually in the portal first as it created the API connection that was then used in the Logic App.
resource "azurerm_logic_app_workflow" "ads_spend_alert" {
  name                = "ads_spend_alert"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity {
    type = "SystemAssigned"
  }

  parameters = {
    "$connections" = jsonencode({
      sql = {
        connectionId   = "/subscriptions/${var.az_subscription_id}/resourceGroups/GB_Reporting_RG/providers/Microsoft.Web/connections/sql"
        connectionName = "sql"
        connectionProperties = {
          authentication = {
            type = "ManagedServiceIdentity"
          }
        }
        id = "/subscriptions/${var.az_subscription_id}/providers/Microsoft.Web/locations/westeurope/managedApis/sql"
      }
      acsemail = {
        connectionId   = "/subscriptions/${var.az_subscription_id}/resourceGroups/GB_Reporting_RG/providers/Microsoft.Web/connections/acsemail"
        connectionName = "acsemail"
        id             = "/subscriptions/${var.az_subscription_id}/providers/Microsoft.Web/locations/westeurope/managedApis/acsemail"
      }
    })
  }
  workflow_parameters = {
    "$connections" = jsonencode(
      {
        defaultValue = {}
        type         = "Object"
      }
    )
  }

  tags = {
    environment = "production"
  }
}

resource "azurerm_logic_app_trigger_recurrence" "ads_spend_alert_trigger" {
  name         = "Every30Min"
  logic_app_id = azurerm_logic_app_workflow.ads_spend_alert.id
  frequency    = "Minute"
  interval     = 30
}


# # SQL Query Step using azurerm_logic_app_action_custom
resource "azurerm_logic_app_action_custom" "ads_alert_check_sql_query" {
  name         = "ads_alert_check_sql_query"
  logic_app_id = azurerm_logic_app_workflow.ads_spend_alert.id
  body = jsonencode(
    {
      inputs = {
        body = {
          query = <<-SQL
            SELECT
                f.account_id,
                a.account_name,
                f.date_id,
                SUM(f.spend) as spend
            FROM
                [dbo].[fact_accounts_insights] as f
                JOIN [dbo].[dim_active_accounts] as a on f.account_id = a.account_id
            WHERE
                CONVERT(date, CONVERT(varchar(8), f.date_id), 112) = CONVERT(date, GETDATE())
            GROUP BY
                f.account_id,
                f.date_id,
                a.account_name
            HAVING
                SUM(f.spend) > 40000;
          SQL
        }
        host = {
          connection = {
            name = "@parameters('$connections')['sql']['connectionId']"
          }
        }
        method = "post"
        path   = "/v2/datasets/@{encodeURIComponent(encodeURIComponent('${azurerm_mssql_server.gb-ads-sql-server.fully_qualified_domain_name}'))},@{encodeURIComponent(encodeURIComponent('${azurerm_mssql_database.GB_Reporting_DB.name}'))}/query/sql"
      }
      runAfter = {}
      type     = "ApiConnection"
    }
  )
}

resource "azurerm_logic_app_action_custom" "ads_alert_check_if_query_returns_rows" {
  name         = "Condition"
  logic_app_id = azurerm_logic_app_workflow.ads_spend_alert.id
  body = jsonencode(
    {
      actions = {
        For_each = {
          actions = {
            Send_email-copy = {
              inputs = {
                body = {
                  content = {
                    html    = "<p class=\"editor-paragraph\">Account ID: @{item()?['ad_account_id']}</p><p class=\"editor-paragraph\">Account Name: @{item()?['account_name']}</p><p class=\"editor-paragraph\">Date: @{substring(item()?['date_start'],0,10)}</p><p class=\"editor-paragraph\">Total Spent: @{item()?['total_spend']}</p>"
                    subject = "Spend Alert: Daily threshold reached for @{item()?['account_name']}"
                  }
                  importance = "High"
                  recipients = {
                    to = [
                      {
                        address = "dl_ads_alerts@globalbrother.com"
                      },
                    ]
                  }
                  senderAddress = "DoNotReply@${azurerm_email_communication_service_domain.gb_email_alerts_source_domain.from_sender_domain}"
                }
                host = {
                  connection = {
                    name = "@parameters('$connections')['acsemail']['connectionId']"
                  }
                }
                method = "post"
                path   = "/emails:sendGAVersion"
                queries = {
                  "api-version" = "2023-03-31"
                }
              }
              type = "ApiConnection"
            }
          }
          foreach = "@body('ads_alert_check_sql_query')?['resultsets']?['Table1']"
          type    = "Foreach"
        }
      }
      else = {
        actions = {}
      }
      expression = {
        and = [
          {
            equals = [
              "@empty(body('ads_alert_check_sql_query')?['resultsets']?['Table1'])",
              false,
            ]
          },
        ]
      }
      runAfter = {
        ads_alert_check_sql_query = [
          "Succeeded",
        ]
      }
      type = "If"
    }
  )
}

# Logic App to trigger Budget Alerts
# Similar to ads_spend_alert, but for budget/credit usage monitoring
# I had to add the sql connection manually in the portal first as it created the API connection that was then used in the Logic App.
resource "azurerm_logic_app_workflow" "budget_alert" {
  name                = "budget_alert"
  location            = azurerm_resource_group.GB_Reporting_RG.location
  resource_group_name = azurerm_resource_group.GB_Reporting_RG.name

  identity {
    type = "SystemAssigned"
  }

  parameters = {
    "$connections" = jsonencode({
      sql = {
        connectionId   = "/subscriptions/${var.az_subscription_id}/resourceGroups/GB_Reporting_RG/providers/Microsoft.Web/connections/sql"
        connectionName = "sql"
        connectionProperties = {
          authentication = {
            type = "ManagedServiceIdentity"
          }
        }
        id = "/subscriptions/${var.az_subscription_id}/providers/Microsoft.Web/locations/westeurope/managedApis/sql"
      }
      acsemail = {
        connectionId   = "/subscriptions/${var.az_subscription_id}/resourceGroups/GB_Reporting_RG/providers/Microsoft.Web/connections/acsemail"
        connectionName = "acsemail"
        id             = "/subscriptions/${var.az_subscription_id}/providers/Microsoft.Web/locations/westeurope/managedApis/acsemail"
      }
    })
  }
  workflow_parameters = {
    "$connections" = jsonencode(
      {
        defaultValue = {}
        type         = "Object"
      }
    )
  }

  tags = {
    environment = "production"
  }
}

resource "azurerm_logic_app_trigger_recurrence" "budget_alert_trigger" {
  name         = "Every30Min"
  logic_app_id = azurerm_logic_app_workflow.budget_alert.id
  frequency    = "Minute"
  interval     = 30
}

# Step 1: Call Function App to run budget_alert pipeline
resource "azurerm_logic_app_action_custom" "budget_alert_call_function" {
  name         = "Call_Budget_Alert_Pipeline"
  logic_app_id = azurerm_logic_app_workflow.budget_alert.id
  body = jsonencode({
    type = "Http"
    runAfter = {}
    inputs = {
      uri    = "${var.function_url}"
      method = "POST"
      headers = {
        "Content-Type" = "application/json"
      }
      body = {
        pipeline_name            = "alert_business_budget"
        threshold_percentage     = 80.0
      }
      authentication = {
        type     = "ManagedServiceIdentity"
        audience = var.audience
      }
    }
  })
}

# Step 2: Query SQL for alerts that need to be sent
resource "azurerm_logic_app_action_custom" "budget_alert_check_sql_query" {
  name         = "budget_alert_check_sql_query"
  logic_app_id = azurerm_logic_app_workflow.budget_alert.id
  body = jsonencode({
    inputs = {
      body = {
        query = "SELECT ah.alert_id, ah.business_id, ah.extended_credit_id, ah.usage_percentage, ah.balance_amount, ah.max_balance_amount, db.business_name, bs.legal_entity_name, bs.owner_business_name, bs.balance_currency FROM dim_alert_history ah INNER JOIN dim_business_accounts db ON ah.business_id = db.business_id LEFT JOIN (SELECT DISTINCT business_id, extended_credit_id, legal_entity_name, owner_business_name, balance_currency FROM fact_budget_snapshots WHERE snapshot_date >= DATEADD(day, -1, GETDATE())) bs ON ah.business_id = bs.business_id AND ah.extended_credit_id = bs.extended_credit_id WHERE ah.email_sent = 0 AND CAST(ah.alert_date AS DATE) = CAST(GETDATE() AS DATE) AND ah.alert_type = 'budget_threshold_80';"
      }
      host = {
        connection = {
          name = "@parameters('$connections')['sql']['connectionId']"
        }
      }
      method = "post"
      path   = "/v2/datasets/@{encodeURIComponent(encodeURIComponent('${azurerm_mssql_server.gb-ads-sql-server.fully_qualified_domain_name}'))},@{encodeURIComponent(encodeURIComponent('${azurerm_mssql_database.GB_Reporting_DB.name}'))}/query/sql"
    }
    runAfter = {
      Call_Budget_Alert_Pipeline = ["Succeeded", "Failed", "Skipped", "TimedOut"]
    }
    type = "ApiConnection"
  })
  depends_on = [azurerm_logic_app_action_custom.budget_alert_call_function]
}

# Step 3: Condition - Check if query returns rows and send emails
resource "azurerm_logic_app_action_custom" "budget_alert_check_if_query_returns_rows" {
  name         = "Condition"
  logic_app_id = azurerm_logic_app_workflow.budget_alert.id
  body = jsonencode({
    actions = {
      For_each = {
        actions = {
          Send_email = {
            inputs = {
              body = {
                content = {
                  html = "<p class=\"editor-paragraph\"><strong>⚠️ Budget Alert: Credit Usage Exceeded Threshold</strong></p><p class=\"editor-paragraph\">Business: @{item()?['owner_business_name']}</p><p class=\"editor-paragraph\">Legal Entity: @{item()?['legal_entity_name']}</p><p class=\"editor-paragraph\">Credit ID: @{item()?['extended_credit_id']}</p><p class=\"editor-paragraph\"><br></p><p class=\"editor-paragraph\"><strong>Status:</strong></p><p class=\"editor-paragraph\">- Balance: @{formatNumber(item()?['balance_amount'], 'N2')} @{item()?['balance_currency']}</p><p class=\"editor-paragraph\">- Max Balance: @{formatNumber(item()?['max_balance_amount'], 'N2')} @{item()?['balance_currency']}</p><p class=\"editor-paragraph\">- Usage: @{formatNumber(item()?['usage_percentage'], 'N2')}%</p><p class=\"editor-paragraph\"><br></p><p class=\"editor-paragraph\">⚠️ <strong>WARNING:</strong> The budget has exceeded 50% of the maximum limit!</p>"
                  subject = "Budget Alert: @{item()?['owner_business_name']} - @{formatNumber(item()?['usage_percentage'], 2)}% utilizat"
                }
                importance = "High"
                recipients = {
                  to = [
                    {
                      address = "dl_ads_alerts@globalbrother.com"
                    },
                  ]
                }
                senderAddress = "DoNotReply@${azurerm_email_communication_service_domain.gb_email_alerts_source_domain.from_sender_domain}"
              }
              host = {
                connection = {
                  name = "@parameters('$connections')['acsemail']['connectionId']"
                }
              }
              method = "post"
              path   = "/emails:sendGAVersion"
              queries = {
                "api-version" = "2023-03-31"
              }
            }
            type = "ApiConnection"
          }
          Update_alert_sent = {
            inputs = {
              body = {
                query = "UPDATE dim_alert_history SET email_sent = 1, email_sent_at = GETDATE() WHERE alert_id = @{item()?['alert_id']};"
              }
              host = {
                connection = {
                  name = "@parameters('$connections')['sql']['connectionId']"
                }
              }
              method = "post"
              path   = "/v2/datasets/@{encodeURIComponent(encodeURIComponent('${azurerm_mssql_server.gb-ads-sql-server.fully_qualified_domain_name}'))},@{encodeURIComponent(encodeURIComponent('${azurerm_mssql_database.GB_Reporting_DB.name}'))}/query/sql"
            }
            runAfter = {
              Send_email = ["Succeeded"]
            }
            type = "ApiConnection"
          }
        }
        foreach = "@body('budget_alert_check_sql_query')?['resultsets']?['Table1']"
        type    = "Foreach"
      }
    }
    else = {
      actions = {}
    }
    expression = {
      and = [
        {
          equals = [
            "@empty(body('budget_alert_check_sql_query')?['resultsets']?['Table1'])",
            false,
          ]
        },
      ]
    }
    runAfter = {
      budget_alert_check_sql_query = [
        "Succeeded",
      ]
    }
    type = "If"
  })
  depends_on = [azurerm_logic_app_action_custom.budget_alert_check_sql_query]
}

# RBAC for budget_alert Logic App
module "rbac_budget_alert" {
  source = "./modules/function_rbac"

  logic_app_identity_id = azurerm_logic_app_workflow.budget_alert.identity[0].principal_id
  function_app_name     = azurerm_function_app_flex_consumption.gb_metaads_flex_function.name
  subscription_id       = var.az_subscription_id
}