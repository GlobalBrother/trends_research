/*
 * Settings — Configuration and system management
 * Wired to: /admin/azure/status, /admin/azure/migrate, /admin/azure/diagnose,
 *           /auth/users (CRUD), /import_tokens
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
  Users,
  UserPlus,
  Trash2,
  Upload,
  FileJson,
  Shield,
  ShieldCheck,
  Activity,
  Clock,
  Info,
} from "lucide-react";
import { useState, useCallback, useRef } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { useApi, useLazyApi } from "@/hooks/useApi";
import { useTheme } from "@/contexts/ThemeContext";
import {
  getAzureStatus,
  triggerMigration,
  triggerDiagnose,
  triggerScrape,
  testScraper,
  listUsers,
  addUser,
  updateUserRole,
  deleteUser,
  importTokens,
  getScrapeRuns,
  type AuthUser,
  type ScrapeRun,
} from "@/lib/api";

export default function Settings() {
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const { theme, setTheme } = useTheme();

  // ── Database status ────────────────────────────────────────────────────
  const {
    data: azureData,
    loading: azureLoading,
    error: azureError,
    refetch: refetchAzure,
  } = useApi(() => getAzureStatus(), []);

  const { loading: migrating, execute: doMigrate } = useLazyApi(
    () => triggerMigration()
  );
  const { loading: diagnosing, execute: doDiagnose } = useLazyApi(
    () => triggerDiagnose()
  );

  const dbConnected = azureData?.connected ?? false;
  const tables = azureData?.tables ?? {};
  const tableNames = Object.keys(tables);
  const totalRecords = Object.values(tables).reduce(
    (s: number, v: unknown) => s + (typeof v === "number" ? v : 0),
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
        const passed = res.checks.filter((c: { passed: boolean }) => c.passed).length;
        const total = res.checks.length;
        toast.info(`Diagnosis: ${passed}/${total} checks passed`);
      } else {
        toast.success("Diagnosis complete");
      }
    } catch {
      toast.error("Diagnosis failed");
    }
  };

  const { execute: doSync } = useLazyApi(
    (args: { niche: string; scraper_type: string }) =>
      triggerScrape({ niche: args.niche, geo: "US", scraper_type: args.scraper_type })
  );
  const [scrapingMap, setScrapingMap] = useState<Record<string, boolean>>({});
  const [testingMap, setTestingMap] = useState<Record<string, boolean>>({});
  const [testResultMap, setTestResultMap] = useState<Record<string, { ok: boolean; message: string } | null>>({});

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

  // ── User Management ────────────────────────────────────────────────────
  const {
    data: usersData,
    loading: usersLoading,
    refetch: refetchUsers,
  } = useApi(() => listUsers(), []);

  const users: AuthUser[] = Array.isArray(usersData) ? usersData : [];

  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("trends");
  const [addingUser, setAddingUser] = useState(false);
  const [deletingEmail, setDeletingEmail] = useState<string | null>(null);
  const [updatingEmail, setUpdatingEmail] = useState<string | null>(null);

  const handleAddUser = async () => {
    if (!newEmail.trim()) {
      toast.error("Please enter an email address");
      return;
    }
    setAddingUser(true);
    try {
      await addUser(newEmail.trim(), newRole);
      toast.success(`User ${newEmail} added`);
      setNewEmail("");
      setNewRole("trends");
      refetchUsers();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to add user";
      toast.error(msg);
    } finally {
      setAddingUser(false);
    }
  };

  const handleDeleteUser = async (email: string) => {
    setDeletingEmail(email);
    try {
      await deleteUser(email);
      toast.success(`User ${email} removed`);
      refetchUsers();
    } catch {
      toast.error("Failed to remove user");
    } finally {
      setDeletingEmail(null);
    }
  };

  const handleUpdateRole = async (email: string, role: string) => {
    setUpdatingEmail(email);
    try {
      await updateUserRole(email, role);
      toast.success(`Role updated for ${email}`);
      refetchUsers();
    } catch {
      toast.error("Failed to update role");
    } finally {
      setUpdatingEmail(null);
    }
  };

  // ── Import Tokens ──────────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importGeo, setImportGeo] = useState("US");
  const [importing, setImporting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleImport = useCallback(async () => {
    if (!selectedFile) {
      toast.error("Please select a JSON file first");
      return;
    }
    setImporting(true);
    try {
      const res = await importTokens(selectedFile, importGeo);
      toast.success(res.data.message || "Import started!");
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Import failed";
      toast.error(msg);
    } finally {
      setImporting(false);
    }
  }, [selectedFile, importGeo]);

  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Configure data sources, API keys, user access, and system preferences.
        </p>
      </div>

      <Tabs defaultValue="general" className="space-y-4">
        <TabsList className="h-9 flex-wrap">
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
          <TabsTrigger value="users" className="text-xs gap-1.5">
            <Users className="w-3.5 h-3.5" /> Users
          </TabsTrigger>
          <TabsTrigger value="import" className="text-xs gap-1.5">
            <Upload className="w-3.5 h-3.5" /> Import
          </TabsTrigger>
          <TabsTrigger value="monitor" className="text-xs gap-1.5">
            <Activity className="w-3.5 h-3.5" /> Scrape Monitor
          </TabsTrigger>
        </TabsList>

        {/* ── General ──────────────────────────────────────────────────── */}
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
                <Switch
                  checked={theme === "dark"}
                  onCheckedChange={(checked) => setTheme?.(checked ? "dark" : "light")}
                />
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

        {/* ── Data Sources ─────────────────────────────────────────────── */}
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
              const count = tables[tableKey] ?? tables[source.name] ?? "\u2014";
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
                      variant="outline"
                      size="sm"
                      className="h-7 text-[10px] gap-1"
                      disabled={!!testingMap[source.scraper]}
                      onClick={async () => {
                        setTestingMap((prev) => ({ ...prev, [source.scraper]: true }));
                        setTestResultMap((prev) => ({ ...prev, [source.scraper]: null }));
                        try {
                          const res = await testScraper(source.scraper);
                          const result = res.data;
                          setTestResultMap((prev) => ({ ...prev, [source.scraper]: result }));
                          if (result.ok) {
                            toast.success(`${source.name}: ${result.message}`);
                          } else {
                            toast.error(`${source.name}: ${result.message}`);
                          }
                        } catch {
                          const errResult = { ok: false, message: "Request failed. Server may be unreachable." };
                          setTestResultMap((prev) => ({ ...prev, [source.scraper]: errResult }));
                          toast.error(`${source.name}: Request failed`);
                        } finally {
                          setTestingMap((prev) => ({ ...prev, [source.scraper]: false }));
                        }
                      }}
                    >
                      {testingMap[source.scraper] ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Stethoscope className="w-3 h-3" />
                      )}
                      Test
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-[10px] gap-1"
                      disabled={!!scrapingMap[source.scraper]}
                      onClick={async () => {
                        setScrapingMap((prev) => ({ ...prev, [source.scraper]: true }));
                        try {
                          await doSync({ niche: "technology", scraper_type: source.scraper });
                          toast.success(`${source.name} scrape started`);
                        } catch {
                          toast.error(`Failed to start ${source.name} scrape`);
                        } finally {
                          setScrapingMap((prev) => ({ ...prev, [source.scraper]: false }));
                        }
                      }}
                    >
                      {scrapingMap[source.scraper] ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Play className="w-3 h-3" />
                      )}
                      Scrape
                    </Button>
                  </div>
                  {testResultMap[source.scraper] && (
                    <div className={`col-span-12 text-[10px] px-2 py-1.5 rounded border ${
                      testResultMap[source.scraper]!.ok
                        ? "bg-success/5 border-success/20 text-success"
                        : "bg-destructive/5 border-destructive/20 text-destructive"
                    }`}>
                      <span className="flex items-center gap-1.5">
                        {testResultMap[source.scraper]!.ok ? (
                          <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-3 h-3 flex-shrink-0" />
                        )}
                        {testResultMap[source.scraper]!.message}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </TabsContent>

        {/* ── API Keys ─────────────────────────────────────────────────── */}
        <TabsContent value="keys" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-4 max-w-2xl">
            <h2 className="text-sm font-semibold">API Keys</h2>
            <p className="text-xs text-muted-foreground">
              Manage API keys for external data sources. Keys are loaded from Azure Key Vault at runtime.
            </p>
            {[
              { label: "NewsAPI Key", key: "NEWS_API_KEY", value: "Loaded from Key Vault" },
              { label: "EnsembleData Token", key: "ENSEMBLEDATA_TOKEN", value: "Loaded from Key Vault" },
              { label: "TikTok Client Key", key: "TIKTOK_CLIENT_KEY", value: "Loaded from Key Vault" },
              { label: "GetHookedAI Token", key: "GETHOOKEDAI_TOKEN", value: "Loaded from Key Vault" },
              { label: "Resend API Key", key: "RESEND_API_KEY", value: "Loaded from Key Vault" },
            ].map((apiKey) => (
              <div key={apiKey.key} className="space-y-1.5">
                <Label className="text-xs font-medium">{apiKey.label}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type={showKeys[apiKey.key] ? "text" : "password"}
                    defaultValue={apiKey.value}
                    className="h-8 text-xs font-mono flex-1"
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
              To update keys, rotate the corresponding Azure Key Vault secret and restart the API if the runtime does not reload secrets automatically.
            </p>
          </div>
        </TabsContent>

        {/* ── Database ─────────────────────────────────────────────────── */}
        <TabsContent value="database" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-5 max-w-2xl">
            <h2 className="text-sm font-semibold">Azure SQL Database</h2>

            {azureLoading ? (
              <div className="flex items-center gap-3 p-3 bg-muted/50 border border-border">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Checking connection\u2026</p>
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
                    {String((azureData as unknown as Record<string, unknown>)?.server || "Azure SQL")} &middot; {String((azureData as unknown as Record<string, unknown>)?.database || "Trends_DB")}
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

        {/* ── Users ────────────────────────────────────────────────────── */}
        <TabsContent value="users" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-5 max-w-3xl">
            <div>
              <h2 className="text-sm font-semibold">User Management</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Manage whitelisted users who can access the platform via OTP login.
              </p>
            </div>

            {/* Add user form */}
            <div className="flex items-end gap-2 flex-wrap">
              <div className="flex-1 min-w-[200px] space-y-1">
                <Label className="text-xs">Email</Label>
                <Input
                  type="email"
                  placeholder="user@company.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddUser()}
                  className="h-8 text-sm"
                />
              </div>
              <div className="w-32 space-y-1">
                <Label className="text-xs">Role</Label>
                <Select value={newRole} onValueChange={setNewRole}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="trends">Trends</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={handleAddUser}
                disabled={addingUser}
              >
                {addingUser ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <UserPlus className="w-3.5 h-3.5" />
                )}
                Add User
              </Button>
            </div>

            {/* Users list */}
            {usersLoading ? (
              <div className="flex items-center gap-2 py-6 justify-center text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Loading users...</span>
              </div>
            ) : users.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                No whitelisted users yet. Add one above.
              </div>
            ) : (
              <div className="border border-border rounded-md overflow-hidden">
                <div className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border bg-muted/30 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  <div className="col-span-5">Email</div>
                  <div className="col-span-2">Role</div>
                  <div className="col-span-3">Added</div>
                  <div className="col-span-2 text-right">Actions</div>
                </div>
                {users.map((u) => (
                  <div
                    key={u.email}
                    className="grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border/50 last:border-0 items-center"
                  >
                    <div className="col-span-5 text-sm font-mono truncate" title={u.email}>
                      {u.email}
                    </div>
                    <div className="col-span-2">
                      <Select
                        value={u.role}
                        onValueChange={(val) => handleUpdateRole(u.email, val)}
                        disabled={updatingEmail === u.email}
                      >
                        <SelectTrigger className="h-7 text-[10px] w-24">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="trends">
                            <span className="flex items-center gap-1">
                              <Shield className="w-3 h-3" /> Trends
                            </span>
                          </SelectItem>
                          <SelectItem value="admin">
                            <span className="flex items-center gap-1">
                              <ShieldCheck className="w-3 h-3" /> Admin
                            </span>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="col-span-3 text-xs text-muted-foreground">
                      {u.created_at
                        ? new Date(u.created_at).toLocaleDateString("en", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })
                        : "\u2014"}
                    </div>
                    <div className="col-span-2 flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={() => handleDeleteUser(u.email)}
                        disabled={deletingEmail === u.email}
                        title="Remove user"
                      >
                        {deletingEmail === u.email ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <p className="text-[10px] text-muted-foreground">
              Users with the <strong>Admin</strong> role can manage other users and system settings.
              Users with the <strong>Trends</strong> role can view dashboards and run scrapes.
            </p>
          </div>
        </TabsContent>

        {/* ── Import Tokens ────────────────────────────────────────────── */}
        <TabsContent value="import" className="space-y-4">
          <div className="bg-card border border-border p-5 space-y-5 max-w-2xl">
            <div>
              <h2 className="text-sm font-semibold">Import Google Trends Tokens</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                When the Google Trends API returns a 429 (rate limit) error, you can manually
                download the JSON response from your browser and upload it here. The system will
                extract widget tokens and fetch the trend data using those tokens directly.
              </p>
            </div>

            {/* Instructions */}
            <div className="bg-muted/30 border border-border rounded-md p-4 space-y-2">
              <h3 className="text-xs font-semibold flex items-center gap-1.5">
                <FileJson className="w-3.5 h-3.5" /> How to get the JSON file
              </h3>
              <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
                <li>Open Google Trends in your browser and search for a keyword</li>
                <li>Open DevTools (F12) and go to the Network tab</li>
                <li>Look for the request to <code className="font-mono text-[10px]">trends/api/widgetdata</code> or the main explore request</li>
                <li>Right-click the request and select "Copy response"</li>
                <li>Save the response as a <code className="font-mono text-[10px]">.json</code> file</li>
                <li>Upload the file below</li>
              </ol>
            </div>

            {/* Upload form */}
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs">JSON File</Label>
                <div className="flex items-center gap-2">
                  <Input
                    ref={fileInputRef}
                    type="file"
                    accept=".json,application/json"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                    className="h-9 text-xs file:mr-3 file:h-7 file:px-3 file:rounded file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-medium cursor-pointer"
                  />
                </div>
                {selectedFile && (
                  <p className="text-[10px] text-muted-foreground">
                    Selected: <span className="font-mono">{selectedFile.name}</span> ({(selectedFile.size / 1024).toFixed(1)} KB)
                  </p>
                )}
              </div>

              <div className="flex items-end gap-2">
                <div className="w-24 space-y-1">
                  <Label className="text-xs">Geo</Label>
                  <Input
                    value={importGeo}
                    onChange={(e) => setImportGeo(e.target.value.toUpperCase())}
                    className="h-8 text-xs font-mono"
                    maxLength={5}
                    placeholder="US"
                  />
                </div>
                <Button
                  size="sm"
                  className="h-8 text-xs gap-1.5"
                  onClick={handleImport}
                  disabled={importing || !selectedFile}
                >
                  {importing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Upload className="w-3.5 h-3.5" />
                  )}
                  Import Tokens
                </Button>
              </div>
            </div>

            <p className="text-[10px] text-muted-foreground">
              The import runs in the background. Trend data will appear in the dashboard once processing is complete.
            </p>
          </div>
        </TabsContent>

        {/* ── Scrape Monitor ───────────────────────────────────────────── */}
        <TabsContent value="monitor" className="space-y-4">
          <ScrapeMonitorTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ScrapeMonitorTab() {
  const [params, setParams] = useState({ limit: 50, offset: 0 });
  const { data, loading, refetch } = useApi(() => getScrapeRuns(params), [params]);

  const runs = data?.items || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Individual Scrape Processes</h2>
        <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => refetch()}>
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="bg-card border border-border">
        <div className="grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
          <div className="col-span-2">Source / Mode</div>
          <div className="col-span-2">Time</div>
          <div className="col-span-1 text-center">Status</div>
          <div className="col-span-1 text-right">Fetched</div>
          <div className="col-span-1 text-right">Saved</div>
          <div className="col-span-1 text-right">Failed</div>
          <div className="col-span-1 text-right">Latency</div>
          <div className="col-span-3 text-right">Alerts</div>
        </div>

        {loading && runs.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">Loading monitoring data...</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">No scrape runs found.</div>
        ) : (
          <div className="divide-y divide-border/50">
            {runs.map((run: ScrapeRun) => (
              <div key={run.id} className="grid grid-cols-12 gap-2 px-4 py-3 items-center hover:bg-muted/30 transition-colors">
                <div className="col-span-2">
                  <div className="text-sm font-medium">{run.source}</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-tight">{run.acquisition_mode} {run.country ? `· ${run.country}` : ""}</div>
                </div>
                <div className="col-span-2">
                  <div className="text-xs flex items-center gap-1">
                    <Clock className="w-3 h-3 text-muted-foreground" />
                    {new Date(run.started_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </div>
                  {run.finished_at && (
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      Duration: {Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s
                    </div>
                  )}
                </div>
                <div className="col-span-1 text-center">
                  <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium uppercase ${
                    run.status === "completed" ? "bg-success/10 text-success" :
                    run.status === "failed" ? "bg-danger/10 text-danger" :
                    run.status === "running" ? "bg-blue-500/10 text-blue-500 animate-pulse" :
                    "bg-muted text-muted-foreground"
                  }`}>
                    {run.status}
                  </span>
                </div>
                <div className="col-span-1 text-right text-xs font-mono">{run.fetched_count}</div>
                <div className="col-span-1 text-right text-xs font-mono font-medium text-success">{run.inserted_count}</div>
                <div className="col-span-1 text-right text-xs font-mono text-danger">{run.failed_count > 0 ? run.failed_count : "—"}</div>
                <div className="col-span-1 text-right text-xs font-mono text-muted-foreground">{run.latency_ms ? `${Math.round(run.latency_ms)}ms` : "—"}</div>
                <div className="col-span-3 flex items-center justify-end gap-1.5">
                  {run.alert_state !== "ok" && (
                    <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${
                      run.alert_state === "alert" ? "border-danger/20 bg-danger/5 text-danger" : "border-warning/20 bg-warning/5 text-warning"
                    }`}>
                      <AlertTriangle className="w-3 h-3" />
                      {run.alert_state.toUpperCase()}
                    </span>
                  )}
                  {run.errors && Object.keys(run.errors).length > 0 && (
                    <div className="group relative">
                      <div className="flex items-center gap-1 text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded cursor-help">
                        <Info className="w-3 h-3" /> Errors
                      </div>
                      <div className="absolute right-0 bottom-full mb-2 w-48 bg-popover border border-border p-2 rounded shadow-xl hidden group-hover:block z-50">
                        <div className="text-[10px] font-bold uppercase mb-1 border-b pb-1">Error Types</div>
                        {Object.entries(run.errors).map(([err, count]) => (
                          <div key={err} className="flex justify-between text-[10px] py-0.5">
                            <span className="truncate mr-2">{err}</span>
                            <span className="font-mono font-bold">{count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
