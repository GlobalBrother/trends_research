import { useState } from "react";
import {
  Eye,
  ExternalLink,
  Heart,
  Loader2,
  MessageCircle,
  Share2,
  Shield,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/hooks/useApi";
import {
  getHackerNewsTrends,
  getInstagramPosts,
  getNewsTrends,
  getRedditPosts,
  getRedditTrends,
  getThreadsPosts,
  getTiktokVideos,
  getYoutubeTrends,
  getYoutubeVideos,
  type ContentRow,
} from "@/lib/api";

function formatNumber(value?: number): string {
  if (value == null) return "-";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function timeAgo(dateStr?: string): string {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return date.toLocaleDateString("en", { month: "short", day: "numeric" });
}

function normalizeContentItem(item: ContentRow, platform: string) {
  const record = { ...item } as Record<string, unknown>;
  const text = record.title ?? record.description ?? record.caption ?? record.text_content ?? "";
  const author = record.channel_title ?? record.author_name ?? record.author ?? record.username ?? "";
  const views = Number(record.view_count ?? record.play_count ?? record.views ?? 0);
  const likes = Number(record.like_count ?? record.digg_count ?? record.score ?? record.likes ?? 0);
  const comments = Number(record.comment_count ?? record.num_comments ?? record.reply_count ?? record.comments ?? 0);
  const shares = Number(record.share_count ?? record.repost_count ?? record.shares ?? 0);
  const saves = Number(record.save_count ?? record.collect_count ?? record.quote_count ?? record.saves ?? 0);
  const engagementTotal = Number(record.engagement_total ?? 0) || (views + likes + comments + shares + saves);
  const postedAt = String(record.published ?? record.created ?? record.posted ?? record.created_at ?? "");
  const topic = String(record.subreddit ?? record.keyword ?? "");
  const followers = Number(record.follower_count ?? 0);

  return {
    text: String(text),
    author: String(author),
    views,
    likes,
    comments,
    shares,
    saves,
    engagementTotal,
    postedAt,
    topic,
    followers,
    isVerified: Boolean(record.is_verified),
    profilePic: String(record.profile_pic_url ?? ""),
    url: String(record.url ?? ""),
    mediaType: String(record.media_type ?? ""),
    platform,
  };
}

function ContentCard({ item, platform }: { item: ContentRow; platform: string }) {
  const normalized = normalizeContentItem(item, platform);
  const truncated = normalized.text.length > 200 ? `${normalized.text.slice(0, 200)}...` : normalized.text || "-";
  const engagementRate = normalized.views > 0 ? ((normalized.likes + normalized.comments) / normalized.views) * 100 : 0;
  const engagementLabel = engagementRate > 10 ? "Hot" : engagementRate > 5 ? "High" : engagementRate > 1 ? "Good" : normalized.views > 0 ? "Low" : null;
  const engagementColor = engagementRate > 10
    ? "text-red-500 bg-red-500/10"
    : engagementRate > 5
      ? "text-orange-500 bg-orange-500/10"
      : engagementRate > 1
        ? "text-green-500 bg-green-500/10"
        : "text-muted-foreground bg-muted";

  return (
    <div className="bg-card border border-border p-3 space-y-2.5 hover:border-primary/30 transition-colors rounded-md">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          {normalized.profilePic && (
            <img src={normalized.profilePic} alt="" className="w-5 h-5 rounded-full object-cover shrink-0" />
          )}
          <div className="flex items-center gap-1 min-w-0">
            {normalized.author && (
              <span className="text-xs font-medium text-primary truncate">
                @{normalized.author}
              </span>
            )}
            {normalized.isVerified && <Shield className="w-3 h-3 text-blue-500 shrink-0" />}
          </div>
          {normalized.followers > 0 && (
            <span className="text-[9px] text-muted-foreground shrink-0">
              {formatNumber(normalized.followers)} followers
            </span>
          )}
        </div>
        <span className="text-[10px] text-muted-foreground shrink-0 ml-2">{timeAgo(normalized.postedAt)}</span>
      </div>

      {normalized.topic && (
        <span className="inline-block text-[10px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground">
          {platform === "reddit" ? `r/${normalized.topic}` : normalized.topic}
        </span>
      )}

      <p className="text-xs leading-relaxed">{truncated}</p>

      <div className="flex items-center gap-3 text-[10px] text-muted-foreground flex-wrap">
        {normalized.views > 0 && (
          <span className="flex items-center gap-1">
            <Eye className="w-3 h-3" /> {formatNumber(normalized.views)}
          </span>
        )}
        {normalized.likes > 0 && (
          <span className="flex items-center gap-1">
            <Heart className="w-3 h-3" /> {formatNumber(normalized.likes)}
          </span>
        )}
        {normalized.comments > 0 && (
          <span className="flex items-center gap-1">
            <MessageCircle className="w-3 h-3" /> {formatNumber(normalized.comments)}
          </span>
        )}
        {normalized.shares > 0 && (
          <span className="flex items-center gap-1">
            <Share2 className="w-3 h-3" /> {formatNumber(normalized.shares)}
          </span>
        )}
        {normalized.saves > 0 && (
          <span className="flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> {formatNumber(normalized.saves)} saved
          </span>
        )}
      </div>

      <div className="flex items-center justify-between pt-1 border-t border-border/50">
        <div className="flex items-center gap-2">
          {normalized.engagementTotal > 0 && (
            <span className="text-[10px] font-mono text-muted-foreground">
              {formatNumber(normalized.engagementTotal)} total
            </span>
          )}
          {engagementLabel && (
            <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded ${engagementColor}`}>
              {engagementLabel} {engagementRate > 0 ? `(${engagementRate.toFixed(1)}%)` : ""}
            </span>
          )}
          {normalized.mediaType && normalized.mediaType !== "unknown" && (
            <span className="text-[9px] px-1.5 py-0.5 bg-muted rounded text-muted-foreground">
              {normalized.mediaType}
            </span>
          )}
        </div>
        {normalized.url && (
          <a
            href={normalized.url}
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

interface PlatformContentSectionProps {
  selectedNiche: string;
  selectedGeo: string;
}

export default function PlatformContentSection({
  selectedNiche,
  selectedGeo,
}: PlatformContentSectionProps) {
  const [activeTab, setActiveTab] = useState("youtube");
  const [contentLimit, setContentLimit] = useState(50);

  const nicheParam = selectedNiche !== "all-niches" ? selectedNiche : undefined;
  const geoParam = selectedGeo !== "global" ? selectedGeo : undefined;

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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Platform Content & Trends</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Browse scraped content and trends from each platform.
          </p>
        </div>
        <Select value={String(contentLimit)} onValueChange={(value) => setContentLimit(Number(value))}>
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
            {tab.trends.length > 0 && (
              <div className="bg-card border border-border p-3">
                <h3 className="text-xs font-semibold mb-2 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5 text-primary" />
                  {tab.label} Trending Topics
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                  {tab.trends.slice(0, 10).map((trend, index) => (
                    <div key={`${tab.id}-${index}`} className="flex items-center gap-2 text-xs p-2 bg-muted/30 rounded">
                      <span className="w-4 font-mono text-muted-foreground text-[10px]">{index + 1}</span>
                      <span className="flex-1 truncate font-medium">{trend.title || trend.keyword || "-"}</span>
                      {trend.virality_score != null && (
                        <span className="font-mono text-primary text-[10px]">
                          {Number(trend.virality_score).toFixed(1)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {tab.loading || tab.trendsLoading ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                <span className="text-sm">Loading {tab.label} content...</span>
              </div>
            ) : tab.data.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {tab.data.map((item, index) => (
                  <ContentCard key={item.external_id || index} item={item} platform={tab.id} />
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
