/*
 * Trend Explorer - Main research interface
 * Fetches real data from /trends, /niches, /all_trends, and platform-specific endpoints.
 * Heavy widgets are lazy-loaded so charting and platform panels do not bloat the initial page chunk.
 */
import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Filter,
  Globe,
  Loader2,
  Play,
  RotateCcw,
  Search,
  Shield,
  TrendingUp,
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
import { toast } from "sonner";
import { useApi, useLazyApi } from "@/hooks/useApi";
import {
  getNiches,
  getTrends,
  triggerScrape,
  type ScrapeRequest,
  type TrendRow,
} from "@/lib/api";

const TrendExplorerChartPanel = lazy(() => import("@/components/trend-explorer/TrendExplorerChartPanel"));
const OpportunityWorkbench = lazy(() => import("@/components/trend-explorer/OpportunityWorkbench"));
const PlatformContentSection = lazy(() => import("@/components/trend-explorer/PlatformContentSection"));

function groupByDate(rows: TrendRow[]) {
  const buckets: Record<string, Record<string, number>> = {};
  for (const row of rows) {
    const rawDate = row.extracted_at;
    if (!rawDate) continue;
    const date = new Date(String(rawDate));
    if (Number.isNaN(date.getTime())) continue;
    const key = date.toLocaleDateString("en", { month: "short", day: "numeric" });
    if (!buckets[key]) buckets[key] = {};
    const topic = (row.keyword || row.title || "other").slice(0, 30);
    buckets[key][topic] = (buckets[key][topic] || 0) + (row.virality_score ?? row.search_volume ?? 1);
  }
  return Object.entries(buckets)
    .sort(([left], [right]) => new Date(left).getTime() - new Date(right).getTime())
    .map(([date, topics]) => ({ date, ...topics }));
}

function getTopKeywords(rows: TrendRow[], limit = 5): string[] {
  const counts: Record<string, number> = {};
  for (const row of rows) {
    const keyword = row.keyword || row.title;
    if (!keyword) continue;
    counts[keyword] = (counts[keyword] || 0) + (row.virality_score ?? row.search_volume ?? 1);
  }
  return Object.entries(counts)
    .sort(([, left], [, right]) => right - left)
    .slice(0, limit)
    .map(([keyword]) => keyword);
}

function getGeoDistribution(rows: TrendRow[]) {
  const counts: Record<string, number> = {};
  for (const row of rows) {
    const rawGeo = row.geo || "Global";
    const geos: string[] = Array.isArray(rawGeo) ? rawGeo.map(String) : [String(rawGeo)];
    for (const geo of geos) {
      counts[geo || "Global"] = (counts[geo || "Global"] || 0) + 1;
    }
  }
  const sorted = Object.entries(counts).sort(([, left], [, right]) => right - left);
  const max = sorted[0]?.[1] || 1;
  return sorted.slice(0, 8).map(([region, count]) => ({
    region,
    index: Math.round((count / max) * 100),
  }));
}

function getPlatformBreakdown(rows: TrendRow[]) {
  const counts: Record<string, number> = {};
  for (const row of rows) {
    const rawPlatform = row.platform || "Unknown";
    const platforms: string[] = Array.isArray(rawPlatform) ? rawPlatform.map(String) : [String(rawPlatform)];
    for (const platform of platforms) {
      counts[platform] = (counts[platform] || 0) + 1;
    }
  }
  const total = rows.length || 1;
  return Object.entries(counts)
    .sort(([, left], [, right]) => right - left)
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

function PanelFallback({ height = "h-[22rem]" }: { height?: string }) {
  return (
    <div className={`bg-card border border-border p-4 flex items-center justify-center ${height}`}>
      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
    </div>
  );
}

export default function TrendExplorer() {
  const [keyword, setKeyword] = useState("");
  const [selectedNiche, setSelectedNiche] = useState("all-niches");
  const [selectedGeo, setSelectedGeo] = useState("global");
  const [selectedScraper, setSelectedScraper] = useState("all");

  const { data: nichesRaw } = useApi(() => getNiches(), []);
  const niches: string[] = Array.isArray(nichesRaw) ? nichesRaw : [];

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

  const { loading: scraping, execute: doScrape } = useLazyApi(
    useCallback((body: ScrapeRequest) => triggerScrape(body), [])
  );

  const handleScrape = async () => {
    const niche = selectedNiche !== "all-niches" ? selectedNiche : keyword || "technology";
    if (!niche) {
      toast.error("Enter a keyword or select a niche first");
      return;
    }
    try {
      const response = await doScrape({
        niche,
        geo: selectedGeo !== "global" ? selectedGeo.toUpperCase() : "US",
        scraper_type: selectedScraper,
      });
      toast.success(response?.message || "Scrape started!");
    } catch {
      toast.error("Failed to start scrape");
    }
  };

  const chartData = useMemo(() => groupByDate(trends), [trends]);
  const topKeywords = useMemo(() => getTopKeywords(trends, 5), [trends]);
  const geoData = useMemo(() => getGeoDistribution(trends), [trends]);
  const sourceData = useMemo(() => getPlatformBreakdown(trends), [trends]);

  const totalVolume = trends.reduce((sum, row) => sum + (row.search_volume ?? 0), 0);
  const avgVirality =
    trends.length > 0
      ? (trends.reduce((sum, row) => sum + (row.virality_score ?? 0), 0) / trends.length).toFixed(1)
      : "-";
  const uniqueKeywords = new Set(trends.map((row) => row.keyword).filter(Boolean)).size;
  const platformCount = (() => {
    const set = new Set<string>();
    for (const row of trends) {
      const rawPlatform = row.platform;
      if (Array.isArray(rawPlatform)) {
        for (const platform of rawPlatform) set.add(String(platform));
      } else if (rawPlatform) {
        set.add(String(rawPlatform));
      }
    }
    return set.size;
  })();

  return (
    <div className="p-4 lg:p-6 space-y-4">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Trend Research</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Monitor emerging patterns across industries, geographies, and platforms.
        </p>
      </div>

      <div className="sticky top-0 z-10 bg-background py-3 -mx-4 lg:-mx-6 px-4 lg:px-6 border-b border-border">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px] max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="Keyword or topic..."
              className="pl-8 h-8 text-sm"
            />
          </div>
          <Select value={selectedNiche} onValueChange={setSelectedNiche}>
            <SelectTrigger className="w-40 h-8 text-xs">
              <SelectValue placeholder="Niche" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all-niches">All Niches</SelectItem>
              {niches.map((niche) => (
                <SelectItem key={niche} value={niche}>
                  {niche}
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
              {SCRAPER_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
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

      {error && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-destructive/10 border border-destructive/20 rounded-sm text-sm text-destructive">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Total Volume", value: totalVolume > 0 ? totalVolume.toLocaleString() : "-", icon: BarChart3, tip: "Sum of search volume across results" },
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

      <Suspense fallback={<PanelFallback height="h-[26rem]" />}>
        <TrendExplorerChartPanel
          loading={loading}
          selectedNiche={selectedNiche}
          chartData={chartData}
          topKeywords={topKeywords}
          trends={trends}
          colors={PLATFORM_COLORS}
        />
      </Suspense>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border p-4">
          <h3 className="text-xs font-semibold mb-3 flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5" /> Top Regions
          </h3>
          {geoData.length > 0 ? (
            <div className="space-y-2">
              {geoData.map((region, index) => (
                <div key={`${region.region}-${index}`} className="flex items-center gap-2 text-xs">
                  <span className="w-4 text-muted-foreground font-mono">{index + 1}</span>
                  <span className="flex-1 truncate">{region.region}</span>
                  <div className="w-16 h-1 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary/60 rounded-full"
                      style={{ width: `${region.index}%` }}
                    />
                  </div>
                  <span className="font-mono w-8 text-right text-muted-foreground">{region.index}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-4">No geo data</p>
          )}
        </div>

        <div className="bg-card border border-border p-4">
          <h3 className="text-xs font-semibold mb-3">Source Breakdown</h3>
          {sourceData.length > 0 ? (
            <div className="space-y-2.5">
              {sourceData.map((source, index) => (
                <div key={`${source.source}-${index}`}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span>{source.source}</span>
                    <span className="font-mono text-muted-foreground">{source.pct}%</span>
                  </div>
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${source.pct}%`,
                        background: PLATFORM_COLORS[index % PLATFORM_COLORS.length],
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

        <div className="bg-card border border-border p-4">
          <h3 className="text-xs font-semibold mb-3">Recent Trends</h3>
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : trends.length > 0 ? (
              trends.slice(0, 15).map((trend, index) => (
                <div
                  key={`${trend.topic || trend.title || trend.keyword || index}-${index}`}
                  className="flex items-center gap-2 text-xs py-1.5 border-b border-border/30 last:border-0"
                >
                  <span className="flex-1 truncate font-medium">{trend.topic || trend.title || trend.keyword || "-"}</span>
                  <span className="text-muted-foreground shrink-0">
                    {Array.isArray(trend.platform) ? trend.platform.join(", ") : trend.platform}
                  </span>
                  <span className="font-mono shrink-0">
                    {trend.virality_score != null ? Number(trend.virality_score).toFixed(1) : "-"}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground text-center py-4">No trends yet</p>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-border pt-4">
        <Suspense fallback={<PanelFallback height="h-[22rem]" />}>
          <OpportunityWorkbench selectedGeo={selectedGeo} selectedNiche={selectedNiche} />
        </Suspense>
      </div>

      <div className="border-t border-border pt-4">
        <Suspense fallback={<PanelFallback height="h-[22rem]" />}>
          <PlatformContentSection selectedNiche={selectedNiche} selectedGeo={selectedGeo} />
        </Suspense>
      </div>
    </div>
  );
}
