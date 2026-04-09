/*
 * Trend Explorer — Main research interface
 * Fetches real data from /trends, /niches, /all_trends, and platform-specific endpoints.
 * Now includes Platform Content tabs for YouTube, TikTok, Instagram, Reddit, Threads.
 */
import { useState, useMemo, useCallback, useEffect } from "react";
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
  ExternalLink,
  Heart,
  MessageCircle,
  Share2,
  Eye,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  getYoutubeVideos,
  getTiktokVideos,
  getInstagramPosts,
  getRedditPosts,
  getThreadsPosts,
  getYoutubeTrends,
  getHackerNewsTrends,
  getRedditTrends,
  getNewsTrends,
  getClusters,
  getCluster,
  getClusterAds,
  submitClusterFeedback,
  type TrendRow,
  type ContentRow,
  type ClusterRow,
  type ClusterDetail,
  type ClusterAdMatch,
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
    const raw = r.geo || "Global";
    const geos: string[] = Array.isArray(raw)
      ? (raw as string[]).map(String)
      : [String(raw)];
    for (const g of geos) {
      counts[g || "Global"] = (counts[g || "Global"] || 0) + 1;
    }
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
    const raw = r.platform || "Unknown";
    const platforms: string[] = Array.isArray(raw)
      ? (raw as string[]).map(String)
      : [String(raw)];
    for (const p of platforms) {
      counts[p] = (counts[p] || 0) + 1;
    }
  }
  const total = rows.length || 1;
  return Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([source, count]) => ({
      source,
      pct: Math.round((count / total) * 100),
    }));
}

function formatNumber(n?: number): string {
  if (n == null) return "\u2014";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function timeAgo(dateStr?: string): string {
  if (!dateStr) return "\u2014";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString("en", { month: "short", day: "numeric" });
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

/* ── Platform Content Card ──────────────────────────────────────────────── */

/** Normalize platform-specific field names back to common names for display */
function normalizeContentItem(item: ContentRow, platform: string) {
  const r = { ...item } as Record<string, unknown>;
  // Text / title
  const text = r.title ?? r.description ?? r.caption ?? r.text_content ?? "";
  // Author
  const author = r.channel_title ?? r.author_name ?? r.author ?? r.username ?? "";
  // Engagement
  const views = Number(r.view_count ?? r.play_count ?? r.views ?? 0);
  const likes = Number(r.like_count ?? r.digg_count ?? r.score ?? r.likes ?? 0);
  const comments = Number(r.comment_count ?? r.num_comments ?? r.reply_count ?? r.comments ?? 0);
  const shares = Number(r.share_count ?? r.repost_count ?? r.shares ?? 0);
  const saves = Number(r.save_count ?? r.collect_count ?? r.quote_count ?? r.saves ?? 0);
  const engagementTotal = Number(r.engagement_total ?? 0) || (views + likes + comments + shares + saves);
  // Time
  const postedAt = String(r.published ?? r.created ?? r.posted ?? r.created_at ?? "");
  // Topic / category
  const topic = String(r.subreddit ?? r.keyword ?? "");
  // Follower count
  const followers = Number(r.follower_count ?? 0);
  const isVerified = Boolean(r.is_verified);
  const profilePic = String(r.profile_pic_url ?? "");
  const fullName = String(r.full_name ?? "");
  const url = String(r.url ?? "");
  const mediaType = String(r.media_type ?? "");

  return {
    text: String(text),
    author: String(author),
    fullName,
    views,
    likes,
    comments,
    shares,
    saves,
    engagementTotal,
    postedAt,
    topic,
    followers,
    isVerified,
    profilePic,
    url,
    mediaType,
  };
}

function ContentCard({ item, platform }: { item: ContentRow; platform: string }) {
  const n = normalizeContentItem(item, platform);
  const truncated = n.text.length > 200 ? n.text.slice(0, 200) + "\u2026" : n.text || "\u2014";

  // Engagement rate estimate (likes+comments / views) if views > 0
  const engRate = n.views > 0 ? ((n.likes + n.comments) / n.views) * 100 : 0;
  const engLabel = engRate > 10 ? "Hot" : engRate > 5 ? "High" : engRate > 1 ? "Good" : n.views > 0 ? "Low" : null;
  const engColor = engRate > 10
    ? "text-red-500 bg-red-500/10"
    : engRate > 5
    ? "text-orange-500 bg-orange-500/10"
    : engRate > 1
    ? "text-green-500 bg-green-500/10"
    : "text-muted-foreground bg-muted";

  return (
    <div className="bg-card border border-border p-3 space-y-2.5 hover:border-primary/30 transition-colors rounded-md">
      {/* Header: author + verified + topic + time */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          {n.profilePic && (
            <img src={n.profilePic} alt="" className="w-5 h-5 rounded-full object-cover shrink-0" />
          )}
          <div className="flex items-center gap-1 min-w-0">
            {n.author && (
              <span className="text-xs font-medium text-primary truncate">
                @{n.author}
              </span>
            )}
            {n.isVerified && (
              <Shield className="w-3 h-3 text-blue-500 shrink-0" />
            )}
          </div>
          {n.followers > 0 && (
            <span className="text-[9px] text-muted-foreground shrink-0">
              {formatNumber(n.followers)} followers
            </span>
          )}
        </div>
        <span className="text-[10px] text-muted-foreground shrink-0 ml-2">{timeAgo(n.postedAt)}</span>
      </div>

      {/* Topic tag */}
      {n.topic && (
        <span className="inline-block text-[10px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground">
          {platform === "reddit" ? `r/${n.topic}` : n.topic}
        </span>
      )}

      {/* Content text */}
      <p className="text-xs leading-relaxed">{truncated}</p>

      {/* Engagement stats row */}
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground flex-wrap">
        {n.views > 0 && (
          <span className="flex items-center gap-1">
            <Eye className="w-3 h-3" /> {formatNumber(n.views)}
          </span>
        )}
        {n.likes > 0 && (
          <span className="flex items-center gap-1">
            <Heart className="w-3 h-3" /> {formatNumber(n.likes)}
          </span>
        )}
        {n.comments > 0 && (
          <span className="flex items-center gap-1">
            <MessageCircle className="w-3 h-3" /> {formatNumber(n.comments)}
          </span>
        )}
        {n.shares > 0 && (
          <span className="flex items-center gap-1">
            <Share2 className="w-3 h-3" /> {formatNumber(n.shares)}
          </span>
        )}
        {n.saves > 0 && (
          <span className="flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> {formatNumber(n.saves)} saved
          </span>
        )}
      </div>

      {/* Insights row: engagement rate + total + link */}
      <div className="flex items-center justify-between pt-1 border-t border-border/50">
        <div className="flex items-center gap-2">
          {n.engagementTotal > 0 && (
            <span className="text-[10px] font-mono text-muted-foreground">
              {formatNumber(n.engagementTotal)} total
            </span>
          )}
          {engLabel && (
            <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded ${engColor}`}>
              {engLabel} {engRate > 0 ? `(${engRate.toFixed(1)}%)` : ""}
            </span>
          )}
          {n.mediaType && n.mediaType !== "unknown" && (
            <span className="text-[9px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground">
              {n.mediaType}
            </span>
          )}
        </div>
        {n.url && (
          <a
            href={n.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[10px] text-primary hover:underline"
          >
            <ExternalLink className="w-3 h-3" /> View
          </a>
        )}
      </div>
    </div>
  );
}

/* ── Platform Content Section ───────────────────────────────────────────── */

function PlatformContentSection({
  selectedNiche,
  selectedGeo,
}: {
  selectedNiche: string;
  selectedGeo: string;
}) {
  const [activeTab, setActiveTab] = useState("youtube");
  const [contentLimit, setContentLimit] = useState(50);

  const nicheParam = selectedNiche !== "all-niches" ? selectedNiche : undefined;
  const geoParam = selectedGeo !== "global" ? selectedGeo : undefined;

  // Fetch content for each platform
  const { data: ytData, loading: ytLoading } = useApi(
    () => getYoutubeVideos({ niche_name: nicheParam, geo: geoParam, limit: contentLimit }),
    [nicheParam, geoParam, contentLimit]
  );
  const { data: ttData, loading: ttLoading } = useApi(
    () => getTiktokVideos({ niche_name: nicheParam, geo: geoParam, limit: contentLimit }),
    [nicheParam, geoParam, contentLimit]
  );
  const { data: igData, loading: igLoading } = useApi(
    () => getInstagramPosts({ niche_name: nicheParam, geo: geoParam, limit: contentLimit }),
    [nicheParam, geoParam, contentLimit]
  );
  const { data: rdData, loading: rdLoading } = useApi(
    () => getRedditPosts({ niche_name: nicheParam, geo: geoParam, limit: contentLimit }),
    [nicheParam, geoParam, contentLimit]
  );
  const { data: thData, loading: thLoading } = useApi(
    () => getThreadsPosts({ niche_name: nicheParam, geo: geoParam, limit: contentLimit }),
    [nicheParam, geoParam, contentLimit]
  );

  // Fetch platform-specific trends
  const { data: ytTrends, loading: ytTrendsLoading } = useApi(
    () => getYoutubeTrends({ niche_name: nicheParam, geo: geoParam }),
    [nicheParam, geoParam]
  );
  const { data: hnTrends, loading: hnTrendsLoading } = useApi(
    () => getHackerNewsTrends({ niche_name: nicheParam, geo: geoParam }),
    [nicheParam, geoParam]
  );
  const { data: rdTrends, loading: rdTrendsLoading } = useApi(
    () => getRedditTrends({ niche_name: nicheParam, geo: geoParam }),
    [nicheParam, geoParam]
  );
  const { data: newsTrends, loading: newsTrendsLoading } = useApi(
    () => getNewsTrends({ niche_name: nicheParam, geo: geoParam }),
    [nicheParam, geoParam]
  );

  const platformTabs = [
    { id: "youtube", label: "YouTube", data: ytData?.data ?? [], loading: ytLoading, trends: ytTrends?.data ?? [], trendsLoading: ytTrendsLoading },
    { id: "tiktok", label: "TikTok", data: ttData?.data ?? [], loading: ttLoading, trends: [], trendsLoading: false },
    { id: "instagram", label: "Instagram", data: igData?.data ?? [], loading: igLoading, trends: [], trendsLoading: false },
    { id: "reddit", label: "Reddit", data: rdData?.data ?? [], loading: rdLoading, trends: rdTrends?.data ?? [], trendsLoading: rdTrendsLoading },
    { id: "threads", label: "Threads", data: thData?.data ?? [], loading: thLoading, trends: [], trendsLoading: false },
    { id: "hackernews", label: "Hacker News", data: [], loading: false, trends: hnTrends?.data ?? [], trendsLoading: hnTrendsLoading },
    { id: "news", label: "News", data: [], loading: false, trends: newsTrends?.data ?? [], trendsLoading: newsTrendsLoading },
  ];

  const active = platformTabs.find((t) => t.id === activeTab) ?? platformTabs[0];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Platform Content & Trends</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Browse scraped content and trends from each platform.
          </p>
        </div>
        <Select value={String(contentLimit)} onValueChange={(v) => setContentLimit(Number(v))}>
          <SelectTrigger className="w-24 h-7 text-[10px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="25">25</SelectItem>
            <SelectItem value="50">50</SelectItem>
            <SelectItem value="100">100</SelectItem>
            <SelectItem value="200">200</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="h-8 flex-wrap">
          {platformTabs.map((tab) => (
            <TabsTrigger key={tab.id} value={tab.id} className="text-[10px] gap-1 px-2">
              {tab.label}
              {(tab.data.length > 0 || tab.trends.length > 0) && (
                <span className="ml-1 text-[9px] font-mono bg-primary/10 text-primary px-1 rounded">
                  {tab.data.length + tab.trends.length}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        {platformTabs.map((tab) => (
          <TabsContent key={tab.id} value={tab.id} className="space-y-3 mt-3">
            {/* Platform trends summary */}
            {tab.trends.length > 0 && (
              <div className="bg-card border border-border p-3">
                <h3 className="text-xs font-semibold mb-2 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5 text-primary" />
                  {tab.label} Trending Topics
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  {tab.trends.slice(0, 10).map((t, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 text-xs p-2 bg-muted/30 rounded"
                    >
                      <span className="w-4 font-mono text-muted-foreground text-[10px]">{i + 1}</span>
                      <span className="flex-1 truncate font-medium">{t.title || t.keyword || "\u2014"}</span>
                      {t.virality_score != null && (
                        <span className="font-mono text-primary text-[10px]">
                          {Number(t.virality_score).toFixed(1)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Platform content cards */}
            {tab.loading || tab.trendsLoading ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                <span className="text-sm">Loading {tab.label} content...</span>
              </div>
            ) : tab.data.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {tab.data.map((item, i) => (
                  <ContentCard key={item.external_id || i} item={item} platform={tab.id} />
                ))}
              </div>
            ) : tab.trends.length === 0 ? (
              <div className="text-center py-12 text-sm text-muted-foreground">
                No {tab.label} content found. Try selecting a niche and running a scrape.
              </div>
            ) : null}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

/* ── component ───────────────────────────────────────────────────────────── */

function OpportunityWorkbench({
  selectedGeo,
}: {
  selectedGeo: string;
}) {
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const { data: clustersData, loading: clustersLoading, refetch: refetchClusters } = useApi(
    () => getClusters({ limit: 8 }),
    [selectedGeo]
  );
  const clusters: ClusterRow[] = clustersData?.data ?? [];

  useEffect(() => {
    if (!selectedClusterId && clusters.length > 0) {
      setSelectedClusterId(clusters[0].id);
    }
  }, [clusters, selectedClusterId]);

  const { data: clusterDetail } = useApi(
    () => selectedClusterId ? getCluster(selectedClusterId) : Promise.resolve({ data: null } as never),
    [selectedClusterId]
  );
  const { data: adsData } = useApi(
    () => selectedClusterId ? getClusterAds(selectedClusterId, 6) : Promise.resolve({ data: { data: [] } } as never),
    [selectedClusterId]
  );
  const { loading: feedbackLoading, execute: sendFeedback } = useLazyApi(submitClusterFeedback);

  const detail = clusterDetail as ClusterDetail | null;
  const ads: ClusterAdMatch[] = adsData?.data ?? [];

  const handleFeedback = async (useful: boolean) => {
    if (!selectedClusterId) return;
    try {
      await sendFeedback(selectedClusterId, {
        useful,
        rating: useful ? 5 : 2,
        used_in_campaign: false,
      });
      toast.success("Feedback saved");
    } catch {
      toast.error("Failed to save feedback");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Ad Opportunities</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Cluster-level opportunities with explainable scoring and competitor evidence.
          </p>
        </div>
        <Button size="sm" variant="outline" className="h-8 text-xs gap-1" onClick={refetchClusters}>
          <RotateCcw className="w-3 h-3" />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-5 bg-card border border-border p-4 space-y-3">
          {clustersLoading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              Loading opportunities...
            </div>
          ) : clusters.length > 0 ? (
            clusters.map((cluster) => (
              <button
                key={cluster.id}
                type="button"
                onClick={() => setSelectedClusterId(cluster.id)}
                className={`w-full text-left border p-3 rounded-md transition-colors ${
                  selectedClusterId === cluster.id ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{cluster.title}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {cluster.platforms.join(", ") || cluster.primary_platform || "Mixed sources"}
                    </p>
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 bg-primary/10 text-primary rounded">
                    {cluster.ad_opportunity_score?.toFixed(1) ?? "—"}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded">{cluster.lifecycle_stage}</span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded">Conf {cluster.confidence_score.toFixed(0)}</span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded">Risk {(cluster.brand_safety_risk ?? 0).toFixed(0)}</span>
                </div>
                {cluster.audience_intent && (
                  <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{cluster.audience_intent}</p>
                )}
              </button>
            ))
          ) : (
            <div className="text-sm text-muted-foreground py-6 text-center">
              No cluster-level opportunities yet. Refresh after trend data is available.
            </div>
          )}
        </div>

        <div className="lg:col-span-7 bg-card border border-border p-4 space-y-4">
          {detail ? (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold">{detail.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Why this matters: {detail.insight?.audience_intent ?? "Signal still forming."}
                  </p>
                </div>
                <div className="text-right text-xs space-y-1">
                  <div>Opportunity: <span className="font-mono">{detail.insight?.ad_opportunity_score?.toFixed(1) ?? "—"}</span></div>
                  <div>Confidence: <span className="font-mono">{detail.confidence_score.toFixed(1)}</span></div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="border border-border rounded-md p-3">
                  <p className="text-muted-foreground">Stage</p>
                  <p className="font-medium mt-1">{detail.lifecycle_stage}</p>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-muted-foreground">Freshness</p>
                  <p className="font-medium mt-1">{detail.freshness_score.toFixed(1)}</p>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-muted-foreground">Saturation Risk</p>
                  <p className="font-medium mt-1">{detail.insight?.saturation_risk?.toFixed(1) ?? "—"}</p>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-muted-foreground">Safety Risk</p>
                  <p className="font-medium mt-1">{detail.insight?.brand_safety_risk?.toFixed(1) ?? "—"}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-border rounded-md p-3">
                  <p className="text-xs font-semibold mb-2">Creative Angles</p>
                  <div className="space-y-2">
                    {(detail.insight?.creative_angle_candidates ?? []).map((angle) => (
                      <div key={angle} className="text-xs text-muted-foreground">{angle}</div>
                    ))}
                  </div>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-xs font-semibold mb-2">Platform Fit</p>
                  <div className="space-y-2">
                    {(detail.insight?.platform_fit ?? []).map((fit) => (
                      <div key={fit.platform} className="flex items-center justify-between text-xs">
                        <span>{fit.platform}</span>
                        <span className="font-mono text-primary">{fit.fit_score.toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="border border-border rounded-md p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold">Competitor Ads</p>
                  <p className="text-[11px] text-muted-foreground">{detail.insight?.ad_timing_window ?? "Monitor timing"}</p>
                </div>
                <div className="space-y-2">
                  {ads.length > 0 ? ads.map(({ match_score, ad }) => (
                    <div key={ad.id} className="flex items-center justify-between gap-3 text-xs border-b border-border/50 pb-2 last:border-0 last:pb-0">
                      <div className="min-w-0">
                        <p className="font-medium truncate">{ad.title || ad.body || "Untitled ad"}</p>
                        <p className="text-muted-foreground truncate">
                          {ad.brand_name || "Unknown brand"} • {ad.display_format || "Unknown format"} • {ad.cta_type || "No CTA"}
                        </p>
                      </div>
                      <span className="font-mono text-primary shrink-0">{match_score.toFixed(1)}</span>
                    </div>
                  )) : (
                    <p className="text-xs text-muted-foreground">No linked ads yet for this cluster.</p>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Feedback: {detail.feedback_summary.count} votes
                  {detail.feedback_summary.avg_rating != null ? ` • Avg ${detail.feedback_summary.avg_rating.toFixed(1)}` : ""}
                </p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => handleFeedback(true)} disabled={feedbackLoading}>
                    Useful
                  </Button>
                  <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => handleFeedback(false)} disabled={feedbackLoading}>
                    Not Useful
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="text-sm text-muted-foreground py-8 text-center">
              Select an opportunity to inspect the structured insight and linked ads.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

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
      : "\u2014";
  const uniqueKeywords = new Set(trends.map((r) => r.keyword).filter(Boolean)).size;
  const platformCount = (() => {
    const set = new Set<string>();
    for (const r of trends) {
      const raw = r.platform;
      if (Array.isArray(raw)) {
        for (const p of raw) set.add(String(p));
      } else if (raw) {
        set.add(String(raw));
      }
    }
    return set.size;
  })();

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
              placeholder="Keyword or topic\u2026"
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
          { label: "Total Volume", value: totalVolume > 0 ? totalVolume.toLocaleString() : "\u2014", icon: BarChart3, tip: "Sum of search volume across results" },
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
                     <span className="flex-1 truncate font-medium">{t.topic || t.title || t.keyword || "—"}</span>
                  <span className="text-muted-foreground shrink-0">
                    {Array.isArray(t.platform) ? (t.platform as string[]).join(", ") : t.platform}
                  </span>
                  <span className="font-mono shrink-0">
                    {t.virality_score != null ? Number(t.virality_score).toFixed(1) : "\u2014"}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground text-center py-4">No trends yet</p>
            )}
          </div>
        </div>
      </div>

      {/* ── Platform Content Section ─────────────────────────────────────── */}
      <div className="border-t border-border pt-4">
        <OpportunityWorkbench selectedGeo={selectedGeo} />
      </div>

      <div className="border-t border-border pt-4">
        <PlatformContentSection selectedNiche={selectedNiche} selectedGeo={selectedGeo} />
      </div>
    </div>
  );
}
