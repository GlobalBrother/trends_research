/*
 * Trend Explorer — Main research interface
 * Fetches real data from /trends, /niches, /all_trends, and platform-specific endpoints.
 */
import { useState, useMemo, useCallback } from "react";
import {
  Search,
  Filter,
  RotateCcw,
  TrendingUp,
  BarChart3,
  Shield,
  ThumbsUp,
  Sparkles,
  AlertTriangle,
  Lightbulb,
  Target,
  ChevronRight,
  Globe,
  Loader2,
  Play,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { toast } from "sonner";
import { useApi, useLazyApi } from "@/hooks/useApi";
import {
  getTrends,
  getNiches,
  triggerScrape,
  type TrendRow,
  type ScrapeRequest,
} from "@/lib/api";

/* ── helpers ─────────────────────────────────────────────────────────────── */

function groupByDate(rows: TrendRow[]) {
  const buckets: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const d = r.extracted_at;
    if (!d) continue;
    const dt = new Date(String(d));
    if (isNaN(dt.getTime())) continue;
    const key = dt.toLocaleDateString("en", { month: "short", day: "numeric" });
    if (!buckets[key]) buckets[key] = {};
    const topic = (r.keyword || r.title || "other").slice(0, 30);
    buckets[key][topic] = (buckets[key][topic] || 0) + (r.virality_score ?? r.search_volume ?? 1);
  }
  return Object.entries(buckets)
    .sort(([a], [b]) => new Date(a).getTime() - new Date(b).getTime())
    .map(([date, topics]) => ({ date, ...topics }));
}

function getTopKeywords(rows: TrendRow[], n = 5): string[] {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const kw = r.keyword || r.title;
    if (!kw) continue;
    counts[kw] = (counts[kw] || 0) + (r.virality_score ?? r.search_volume ?? 1);
  }
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, n)
    .map(([k]) => k);
}

function getGeoDistribution(rows: TrendRow[]) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const g = r.geo || "Global";
    counts[g] = (counts[g] || 0) + 1;
  }
  const sorted = Object.entries(counts).sort(([, a], [, b]) => b - a);
  const max = sorted[0]?.[1] || 1;
  return sorted.slice(0, 8).map(([region, count]) => ({
    region,
    index: Math.round((count / max) * 100),
  }));
}

function getPlatformBreakdown(rows: TrendRow[]) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const p = r.platform || "Unknown";
    counts[p] = (counts[p] || 0) + 1;
  }
  const total = rows.length || 1;
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([source, count]) => ({
      source,
      pct: Math.round((count / total) * 100),
    }));
}

const PLATFORM_COLORS = [
  "oklch(0.50 0.20 260)",
  "oklch(0.60 0.22 20)",
  "oklch(0.72 0.17 70)",
  "oklch(0.65 0.15 170)",
  "oklch(0.55 0.18 300)",
  "oklch(0.55 0.25 320)",
];

const SCRAPER_OPTIONS = [
  { value: "all", label: "All Sources" },
  { value: "google_trends", label: "Google Trends" },
  { value: "youtube", label: "YouTube" },
  { value: "reddit", label: "Reddit" },
  { value: "hackernews", label: "Hacker News" },
  { value: "news", label: "NewsAPI" },
  { value: "TikTok", label: "TikTok" },
  { value: "Instagram", label: "Instagram" },
  { value: "Threads", label: "Threads" },
];

/* ── component ───────────────────────────────────────────────────────────── */

export default function TrendExplorer() {
  const [keyword, setKeyword] = useState("");
  const [selectedNiche, setSelectedNiche] = useState("all-niches");
  const [selectedGeo, setSelectedGeo] = useState("global");
  const [selectedScraper, setSelectedScraper] = useState("all");

  // Fetch niches for the dropdown
  const { data: nichesRaw } = useApi(() => getNiches(), []);
  const niches: string[] = Array.isArray(nichesRaw) ? nichesRaw : [];

  // Fetch trends
  const {
    data: trendsData,
    loading,
    error,
    refetch,
  } = useApi(
    () =>
      getTrends({
        niche_name: selectedNiche !== "all-niches" ? selectedNiche : undefined,
        geo: selectedGeo !== "global" ? selectedGeo : undefined,
      }),
    [selectedNiche, selectedGeo]
  );

  const trends = trendsData?.data ?? [];

  // Scrape trigger
  const { loading: scraping, execute: doScrape } = useLazyApi(
    useCallback(
      (body: ScrapeRequest) => triggerScrape(body),
      []
    )
  );

  const handleScrape = async () => {
    const niche = selectedNiche !== "all-niches" ? selectedNiche : keyword || "technology";
    if (!niche) {
      toast.error("Enter a keyword or select a niche first");
      return;
    }
    try {
      const res = await doScrape({
        niche,
        geo: selectedGeo !== "global" ? selectedGeo.toUpperCase() : "US",
        scraper_type: selectedScraper,
      });
      toast.success(res?.message || "Scrape started!");
    } catch {
      toast.error("Failed to start scrape");
    }
  };

  // Derived data
  const chartData = useMemo(() => groupByDate(trends), [trends]);
  const topKeywords = useMemo(() => getTopKeywords(trends, 5), [trends]);
  const geoData = useMemo(() => getGeoDistribution(trends), [trends]);
  const sourceData = useMemo(() => getPlatformBreakdown(trends), [trends]);

  // KPIs
  const totalVolume = trends.reduce((s, r) => s + (r.search_volume ?? 0), 0);
  const avgVirality =
    trends.length > 0
      ? (trends.reduce((s, r) => s + (r.virality_score ?? 0), 0) / trends.length).toFixed(1)
      : "—";
  const uniqueKeywords = new Set(trends.map((r) => r.keyword).filter(Boolean)).size;
  const platformCount = new Set(trends.map((r) => r.platform).filter(Boolean)).size;

  return (
    <div className="p-4 lg:p-6 space-y-4">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight">Trend Research</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Monitor emerging patterns across industries, geographies, and platforms.
        </p>
      </div>

      {/* Filter bar — sticky */}
      <div className="sticky top-0 z-10 bg-background py-3 -mx-4 lg:-mx-6 px-4 lg:px-6 border-b border-border">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px] max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Keyword or topic…"
              className="pl-8 h-8 text-sm"
            />
          </div>
          <Select value={selectedNiche} onValueChange={setSelectedNiche}>
            <SelectTrigger className="w-40 h-8 text-xs">
              <SelectValue placeholder="Niche" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-niches">All Niches</SelectItem>
              {niches.map((n) => (
                <SelectItem key={n} value={n}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={selectedGeo} onValueChange={setSelectedGeo}>
            <SelectTrigger className="w-32 h-8 text-xs">
              <SelectValue placeholder="Region" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="global">Global</SelectItem>
              <SelectItem value="US">United States</SelectItem>
              <SelectItem value="GB">United Kingdom</SelectItem>
              <SelectItem value="DE">Germany</SelectItem>
              <SelectItem value="IN">India</SelectItem>
              <SelectItem value="RO">Romania</SelectItem>
            </SelectContent>
          </Select>
          <Select value={selectedScraper} onValueChange={setSelectedScraper}>
            <SelectTrigger className="w-36 h-8 text-xs">
              <SelectValue placeholder="Scraper" />
            </SelectTrigger>
            <SelectContent>
              {SCRAPER_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" className="h-8 text-xs gap-1" onClick={refetch} disabled={loading}>
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Filter className="w-3 h-3" />}
            Apply
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs gap-1"
            onClick={handleScrape}
            disabled={scraping}
          >
            {scraping ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            Scrape
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-xs gap-1"
            onClick={() => {
              setKeyword("");
              setSelectedNiche("all-niches");
              setSelectedGeo("global");
              setSelectedScraper("all");
            }}
          >
            <RotateCcw className="w-3 h-3" /> Reset
          </Button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-destructive/10 border border-destructive/20 rounded-sm text-sm text-destructive">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Total Volume", value: totalVolume > 0 ? totalVolume.toLocaleString() : "—", icon: BarChart3, tip: "Sum of search volume across all trends" },
          { label: "Avg Virality", value: avgVirality, icon: TrendingUp, tip: "Average virality score across results" },
          { label: "Keywords", value: String(uniqueKeywords), icon: Shield, tip: "Unique keywords in current results" },
          { label: "Platforms", value: String(platformCount), icon: Globe, tip: "Number of platforms with data" },
        ].map((kpi) => (
          <Tooltip key={kpi.label}>
            <TooltipTrigger asChild>
              <div className="kpi-card">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="section-label">{kpi.label}</span>
                  <kpi.icon className="w-3.5 h-3.5 text-muted-foreground" />
                </div>
                <p className="text-xl font-bold font-mono tracking-tight">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : kpi.value}
                </p>
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p className="text-xs">{kpi.tip}</p>
            </TooltipContent>
          </Tooltip>
        ))}
      </div>

      {/* Main: Chart + Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Chart */}
        <div className="lg:col-span-8 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold">Trend Over Time</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                {selectedNiche !== "all-niches" ? `Niche: ${selectedNiche}` : "All niches"} — top keywords by virality
              </p>
            </div>
          </div>
          <div className="h-72">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <RechartsTooltip
                    contentStyle={{ fontSize: 11, borderRadius: 4, border: "1px solid oklch(0.91 0.005 260)" }}
                  />
                  {topKeywords.map((kw, i) => (
                    <Line
                      key={kw}
                      type="monotone"
                      dataKey={kw}
                      stroke={PLATFORM_COLORS[i % PLATFORM_COLORS.length]}
                      strokeWidth={i === 0 ? 2.5 : 1.5}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No data. Select a niche and click Scrape."}
              </div>
            )}
          </div>
          {topKeywords.length > 0 && (
            <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground flex-wrap">
              {topKeywords.map((kw, i) => (
                <span key={kw} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-0.5 rounded"
                    style={{ background: PLATFORM_COLORS[i % PLATFORM_COLORS.length] }}
                  />
                  {kw.slice(0, 25)}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Top Keywords Panel */}
        <div className="lg:col-span-4 bg-card border border-border p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold">Top Keywords</h2>
          </div>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : trends.length > 0 ? (
            <div className="space-y-2">
              {getTopKeywords(trends, 10).map((kw, i) => {
                const count = trends.filter((r) => r.keyword === kw).length;
                const avgScore =
                  trends
                    .filter((r) => r.keyword === kw)
                    .reduce((s, r) => s + (r.virality_score ?? 0), 0) / (count || 1);
                return (
                  <div key={kw} className="flex items-center gap-2 text-xs">
                    <span className="w-4 font-mono text-muted-foreground">{i + 1}</span>
                    <span className="flex-1 truncate font-medium">{kw}</span>
                    <span className="font-mono text-primary">{avgScore.toFixed(1)}</span>
                    <span className="text-muted-foreground">{count}x</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-4">
              No keywords found. Run a scrape to populate data.
            </p>
          )}
        </div>
      </div>

      {/* Supporting panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Geographic Distribution */}
        <div className="bg-card border border-border p-4">
          <h3 className="text-xs font-semibold mb-3 flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5" /> Top Regions
          </h3>
          {geoData.length > 0 ? (
            <div className="space-y-2">
              {geoData.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="w-4 text-muted-foreground font-mono">{i + 1}</span>
                  <span className="flex-1 truncate">{r.region}</span>
                  <div className="w-16 h-1 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary/60 rounded-full"
                      style={{ width: `${r.index}%` }}
                    />
                  </div>
                  <span className="font-mono w-8 text-right text-muted-foreground">{r.index}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-4">No geo data</p>
          )}
        </div>

        {/* Source Breakdown */}
        <div className="bg-card border border-border p-4">
          <h3 className="text-xs font-semibold mb-3">Source Breakdown</h3>
          {sourceData.length > 0 ? (
            <div className="space-y-2.5">
              {sourceData.map((s, i) => (
                <div key={i}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span>{s.source}</span>
                    <span className="font-mono text-muted-foreground">{s.pct}%</span>
                  </div>
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${s.pct}%`,
                        background: PLATFORM_COLORS[i % PLATFORM_COLORS.length],
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-4">No source data</p>
          )}
        </div>

        {/* Trend Details Table */}
        <div className="bg-card border border-border p-4">
          <h3 className="text-xs font-semibold mb-3">Recent Trends</h3>
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : trends.length > 0 ? (
              trends.slice(0, 15).map((t, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-xs py-1.5 border-b border-border/30 last:border-0"
                >
                  <span className="flex-1 truncate font-medium">{t.title || t.keyword || "—"}</span>
                  <span className="text-muted-foreground shrink-0">{t.platform}</span>
                  <span className="font-mono shrink-0">
                    {t.virality_score != null ? Number(t.virality_score).toFixed(1) : "—"}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground text-center py-4">No trends yet</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
