/*
 * Settings — Configuration and system management
 * Wired to: /admin/azure/status, /admin/azure/migrate, /admin/azure/diagnose
 */
import {
  Settings as SettingsIcon,
  Database,
  Key,
  Globe,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Eye,
  EyeOff,
  Save,
  Loader2,
  Play,
  Stethoscope,
} from "lucide-react";
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { useApi, useLazyApi } from "@/hooks/useApi";
import {
  getAzureStatus,
  triggerMigration,
  triggerDiagnose,
  triggerScrape,
} from "@/lib/api";

export default function Settings() {
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  // Database status — live
  const {
    data: azureData,
    loading: azureLoading,
    error: azureError,
    refetch: refetchAzure,
  } = useApi(() => getAzureStatus(), []);

  // Migration trigger
  const { loading: migrating, execute: doMigrate } = useLazyApi(
    () => triggerMigration()
  );

  // Diagnose trigger
  const { loading: diagnosing, execute: doDiagnose } = useLazyApi(
    () => triggerDiagnose()
  );

  const dbConnected = azureData?.connected ?? false;
  const tables = azureData?.tables ?? {};
  const tableNames = Object.keys(tables);
  const totalRecords = Object.values(tables).reduce(
    (s: number, v: any) => s + (typeof v === "number" ? v : 0),
    0
  );

  const toggleKey = (key: string) => {
    setShowKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleMigrate = async () => {
    try {
      const res = await doMigrate();
      toast.success(res?.message || "Migration completed!");
      refetchAzure();
    } catch {
      toast.error("Migration failed");
    }
  };

  const handleDiagnose = async () => {
    try {
      const res = await doDiagnose();
      if (res?.checks) {
        const passed = res.checks.filter((c: any) => c.passed).length;
        const total = res.checks.length;
        toast.info(`Diagnosis: ${passed}/${total} checks passed`);
      } else {
        toast.success("Diagnosis complete");
      }
    } catch {
      toast.error("Diagnosis failed");
    }
  };

  // Scrape sync buttons
  const { loading: syncing, execute: doSync } = useLazyApi(
    (args: { niche: string; scraper_type: string }) =>
      triggerScrape({ niche: args.niche, geo: "US", scraper_type: args.scraper_type })
  );

  const DATA_SOURCES = [
    { name: "Google Trends", scraper: "google_trends" },
    { name: "Reddit", scraper: "reddit" },
    { name: "Hacker News", scraper: "hackernews" },
    { name: "YouTube", scraper: "youtube" },
    { name: "NewsAPI", scraper: "news" },
    { name: "TikTok", scraper: "TikTok" },
    { name: "Instagram", scraper: "Instagram" },
    { name: "Threads", scraper: "Threads" },
  ];

  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Configure data sources, API keys, and system preferences.
        </p>
      </div>

      <Tabs defaultValue="general" className="space-y-4">
        <TabsList className="h-9">
          <TabsTrigger value="general" className="text-xs gap-1.5">
            <SettingsIcon className="w-3.5 h-3.5" /> General
          </TabsTrigger>
          <TabsTrigger value="sources" className="text-xs gap-1.5">
            <Globe className="w-3.5 h-3.5" /> Data Sources
          </TabsTrigger>
          <TabsTrigger value="keys" className="text-xs gap-1.5">
            <Key className="w-3.5 h-3.5" /> API Keys
          </TabsTrigger>
          <TabsTrigger value="database" className="text-xs gap-1.5">
            <Database className="w-3.5 h-3.5" /> Database
          </TabsTrigger>
        </TabsList>

        {/* General */}
        <TabsContent value="general" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-5 max-w-2xl">
            <h2 className="text-sm font-semibold">General Preferences</h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm">Auto-refresh Dashboard</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Automatically refresh data every 5 minutes
                  </p>
                </div>
                <Switch defaultChecked />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm">Email Notifications</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Receive email alerts for triggered rules
                  </p>
                </div>
                <Switch defaultChecked />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-sm">Dark Mode</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Switch to dark theme
                  </p>
                </div>
                <Switch />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm">Default Time Range</Label>
                <Input defaultValue="30 days" className="max-w-xs h-8 text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm">Default Region</Label>
                <Input defaultValue="Global" className="max-w-xs h-8 text-sm" />
              </div>
            </div>
            <Button size="sm" className="h-8 text-xs gap-1.5" onClick={() => toast("Settings saved")}>
              <Save className="w-3.5 h-3.5" /> Save Changes
            </Button>
          </div>
        </TabsContent>

        {/* Data Sources */}
        <TabsContent value="sources" className="space-y-4">
          <div className="bg-card border border-border">
            <div className="grid grid-cols-12 gap-4 px-4 py-2.5 border-b border-border text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <div className="col-span-3">Source</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2">Records</div>
              <div className="col-span-5 text-right">Actions</div>
            </div>
            {DATA_SOURCES.map((source, i) => {
              const tableKey = source.scraper.toLowerCase();
              const count = tables[tableKey] ?? tables[source.name] ?? "—";
              const hasData = typeof count === "number" && count > 0;
              return (
                <div
                  key={i}
                  className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-border/50 last:border-0 items-center"
                >
                  <div className="col-span-3 text-sm font-medium">{source.name}</div>
                  <div className="col-span-2">
                    <span
                      className={`flex items-center gap-1.5 text-xs ${
                        dbConnected
                          ? hasData
                            ? "text-success"
                            : "text-warning"
                          : "text-danger"
                      }`}
                    >
                      {dbConnected ? (
                        hasData ? (
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        ) : (
                          <AlertTriangle className="w-3.5 h-3.5" />
                        )
                      ) : (
                        <XCircle className="w-3.5 h-3.5" />
                      )}
                      {dbConnected ? (hasData ? "Active" : "No data") : "Offline"}
                    </span>
                  </div>
                  <div className="col-span-2 text-xs font-mono">
                    {typeof count === "number" ? count.toLocaleString() : count}
                  </div>
                  <div className="col-span-5 flex items-center justify-end gap-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-[10px] gap-1"
                      disabled={syncing}
                      onClick={async () => {
                        try {
                          await doSync({ niche: "technology", scraper_type: source.scraper });
                          toast.success(`${source.name} scrape started`);
                        } catch {
                          toast.error(`Failed to start ${source.name} scrape`);
                        }
                      }}
                    >
                      {syncing ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Play className="w-3 h-3" />
                      )}
                      Scrape
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </TabsContent>

        {/* API Keys */}
        <TabsContent value="keys" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-4 max-w-2xl">
            <h2 className="text-sm font-semibold">API Keys</h2>
            <p className="text-xs text-muted-foreground">
              Manage API keys for external data sources. Keys are stored in the server's .env file.
            </p>
            {[
              { label: "NewsAPI Key", key: "NEWS_API_KEY", value: "Set in .env" },
              { label: "EnsembleData Token", key: "ENSEMBLEDATA_TOKEN", value: "Set in .env" },
              { label: "TikTok Client Key", key: "TIKTOK_CLIENT_KEY", value: "Set in .env" },
              { label: "GetHookedAI Token", key: "GETHOOKEDAI_TOKEN", value: "Set in .env" },
              { label: "Resend API Key", key: "RESEND_API_KEY", value: "Set in .env" },
            ].map((apiKey) => (
              <div key={apiKey.key} className="space-y-1.5">
                <Label className="text-xs font-medium">{apiKey.label}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type={showKeys[apiKey.key] ? "text" : "password"}
                    defaultValue={apiKey.value}
                    className="h-8 text-xs font-mono flex-1"
                    readOnly
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0"
                    onClick={() => toggleKey(apiKey.key)}
                  >
                    {showKeys[apiKey.key] ? (
                      <EyeOff className="w-3.5 h-3.5" />
                    ) : (
                      <Eye className="w-3.5 h-3.5" />
                    )}
                  </Button>
                </div>
              </div>
            ))}
            <p className="text-[10px] text-muted-foreground">
              To update keys, edit the <code className="font-mono">.env</code> file on the server and restart the API.
            </p>
          </div>
        </TabsContent>

        {/* Database */}
        <TabsContent value="database" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-5 max-w-2xl">
            <h2 className="text-sm font-semibold">Azure SQL Database</h2>

            {/* Connection status */}
            {azureLoading ? (
              <div className="flex items-center gap-3 p-3 bg-muted/50 border border-border">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Checking connection…</p>
              </div>
            ) : azureError ? (
              <div className="flex items-center gap-3 p-3 bg-destructive/5 border border-destructive/20">
                <XCircle className="w-5 h-5 text-destructive" />
                <div>
                  <p className="text-sm font-medium text-destructive">Connection Error</p>
                  <p className="text-xs text-muted-foreground">{azureError}</p>
                </div>
              </div>
            ) : dbConnected ? (
              <div className="flex items-center gap-3 p-3 bg-success/5 border border-success/20">
                <CheckCircle2 className="w-5 h-5 text-success" />
                <div>
                  <p className="text-sm font-medium text-success">Connected</p>
                  <p className="text-xs text-muted-foreground">
                    {azureData?.server || "Azure SQL"} &middot; {azureData?.database || "Trends_DB"}
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 p-3 bg-warning/5 border border-warning/20">
                <AlertTriangle className="w-5 h-5 text-warning" />
                <div>
                  <p className="text-sm font-medium text-warning">Disconnected</p>
                  <p className="text-xs text-muted-foreground">
                    Cannot reach Azure SQL. Check your connection string and firewall rules.
                  </p>
                </div>
              </div>
            )}

            {/* Table stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="kpi-card">
                <span className="section-label">Total Records</span>
                <p className="text-lg font-bold font-mono mt-1">
                  {azureLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    totalRecords.toLocaleString()
                  )}
                </p>
              </div>
              <div className="kpi-card">
                <span className="section-label">Tables</span>
                <p className="text-lg font-bold font-mono mt-1">
                  {azureLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : tableNames.length}
                </p>
              </div>
              <div className="kpi-card">
                <span className="section-label">Status</span>
                <p className="text-lg font-bold font-mono mt-1">
                  {azureLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : dbConnected ? (
                    "Online"
                  ) : (
                    "Offline"
                  )}
                </p>
              </div>
            </div>

            {/* Table breakdown */}
            {tableNames.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2">Table Breakdown</h3>
                <div className="space-y-1.5">
                  {tableNames.map((name) => (
                    <div key={name} className="flex items-center justify-between text-xs">
                      <span className="font-mono">{name}</span>
                      <span className="font-mono text-muted-foreground">
                        {typeof tables[name] === "number"
                          ? (tables[name] as number).toLocaleString()
                          : tables[name]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5 bg-transparent"
                onClick={refetchAzure}
                disabled={azureLoading}
              >
                {azureLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" />
                )}
                Test Connection
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5 bg-transparent"
                onClick={handleMigrate}
                disabled={migrating}
              >
                {migrating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Database className="w-3.5 h-3.5" />
                )}
                Run Migration
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5 bg-transparent"
                onClick={handleDiagnose}
                disabled={diagnosing}
              >
                {diagnosing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Stethoscope className="w-3.5 h-3.5" />
                )}
                Diagnose
              </Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
