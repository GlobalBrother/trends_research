/*
 * Dashboard — Overview page
 * Fetches real data from the FastAPI backend.
 * Design: KPI strip → Main trend chart + Activity → Top Trends + Momentum
 */
import { useState, useEffect, useMemo } from "react";
import {
  TrendingUp,
  Activity,
  BarChart3,
  Globe,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Loader2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { useApi } from "@/hooks/useApi";
import {
  getTrends,
  getAllTrends,
  getAzureStatus,
  getNiches,
  type TrendRow,
} from "@/lib/api";

const HERO_IMG =
  "https://d2xsxph8kpxj0f.cloudfront.net/310519663454788231/FytdQNpTpcXmkbaLV4kBSe/hero-data-grid_2468fa04.png";

/* ── helpers ─────────────────────────────────────────────────────────────── */

function groupByMonth(rows: TrendRow[]) {
  const buckets: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const d = r.extracted_at || r.created_at;
    if (!d) continue;
    const dt = new Date(String(d));
    if (isNaN(dt.getTime())) continue;
    const key = dt.toLocaleString("en", { month: "short", year: "2-digit" });
    if (!buckets[key]) buckets[key] = {};
    const platform = String(r.platform || "other").toLowerCase();
    buckets[key][platform] = (buckets[key][platform] || 0) + 1;
  }
  return Object.entries(buckets)
    .sort(([a], [b]) => new Date(`1 ${a}`).getTime() - new Date(`1 ${b}`).getTime())
    .map(([date, platforms]) => ({ date, ...platforms }));
}

function topTrends(rows: TrendRow[], n = 8) {
  const scored = rows
    .filter((r) => r.title || r.keyword)
    .map((r) => ({
      name: r.title || r.keyword || "—",
      score: r.virality_score ?? r.search_volume ?? 0,
      platform: String(r.platform || "—"),
      geo: r.geo || "—",
    }));
  scored.sort((a, b) => (b.score as number) - (a.score as number));
  return scored.slice(0, n);
}

/* ── component ───────────────────────────────────────────────────────────── */

export default function Dashboard() {
  const { data: trendsData, loading: trendsLoading, error: trendsError, refetch: refetchTrends } =
    useApi(() => getTrends(), []);
  const { data: allTrendsData, loading: allLoading } = useApi(() => getAllTrends(), []);
  const { data: azureData } = useApi(() => getAzureStatus(), []);
  const { data: nichesData } = useApi(() => getNiches(), []);

  const trends = trendsData?.data ?? [];
  const allTrends = allTrendsData?.data ?? [];

  // KPIs
  const totalTrends = trends.length;
  const avgScore =
    trends.length > 0
      ? (
          trends.reduce((s, r) => s + (r.virality_score ?? 0), 0) / trends.length
        ).toFixed(1)
      : "—";
  const nicheCount = nichesData ? (Array.isArray(nichesData) ? nichesData.length : 0) : 0;
  const dbConnected = azureData?.connected ?? false;
  const tableCount = azureData?.tables ? Object.keys(azureData.tables).length : 0;

  // Chart data
  const chartData = useMemo(() => groupByMonth(allTrends), [allTrends]);
  const platforms = useMemo(() => {
    const set = new Set<string>();
    for (const r of allTrends) {
      if (r.platform) set.add(String(r.platform).toLowerCase());
    }
    return Array.from(set).slice(0, 6);
  }, [allTrends]);

  const PLATFORM_COLORS: Record<string, string> = {
    google_trends: "oklch(0.50 0.20 260)",
    youtube: "oklch(0.60 0.22 25)",
    reddit: "oklch(0.55 0.20 30)",
    hackernews: "oklch(0.65 0.15 70)",
    tiktok: "oklch(0.55 0.25 320)",
    instagram: "oklch(0.60 0.22 340)",
    threads: "oklch(0.50 0.15 200)",
    news: "oklch(0.65 0.15 170)",
  };

  // Top trends
  const top = useMemo(() => topTrends(trends), [trends]);

  // Momentum (weekly count of new trends)
  const momentumData = useMemo(() => {
    const weeks: Record<string, number> = {};
    for (const r of trends) {
      const d = r.extracted_at;
      if (!d) continue;
      const dt = new Date(String(d));
      if (isNaN(dt.getTime())) continue;
      const weekStart = new Date(dt);
      weekStart.setDate(weekStart.getDate() - weekStart.getDay());
      const key = `W${weekStart.toISOString().slice(5, 10)}`;
      weeks[key] = (weeks[key] || 0) + 1;
    }
    return Object.entries(weeks)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-8)
      .map(([date, count]) => ({ date, score: count }));
  }, [trends]);

  const latestMomentum = momentumData.length > 0 ? momentumData[momentumData.length - 1].score : 0;

  const kpiData = [
    { label: "Active Trends", value: totalTrends.toLocaleString(), change: `${trends.length} rows`, up: totalTrends > 0, icon: TrendingUp },
    { label: "Avg Virality", value: String(avgScore), change: "virality score", up: Number(avgScore) > 0, icon: Activity },
    { label: "Niches", value: String(nicheCount), change: `${nicheCount} configured`, up: nicheCount > 0, icon: BarChart3 },
    { label: "Database", value: dbConnected ? "Online" : "Offline", change: `${tableCount} tables`, up: dbConnected, icon: Globe },
  ];

  const isLoading = trendsLoading || allLoading;

  return (
    <div className="p-4 lg:p-6 space-y-6">
      {/* Hero banner */}
      <div
        className="relative overflow-hidden rounded-sm p-6 lg:p-8"
        style={{
          backgroundImage: `url(${HERO_IMG})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
              Intelligence Dashboard
            </h1>
            <p className="mt-1 text-sm text-white/70 max-w-lg">
              Real-time overview of trend signals across all monitored sources and topics.
            </p>
          </div>
          <button
            onClick={refetchTrends}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs rounded transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {trendsError && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-destructive/10 border border-destructive/20 rounded-sm text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Failed to fetch trends: {trendsError}</span>
          <button onClick={refetchTrends} className="ml-auto text-xs underline">
            Retry
          </button>
        </div>
      )}

      {/* KPI Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kpiData.map((kpi) => (
          <div key={kpi.label} className="kpi-card">
            <div className="flex items-center justify-between mb-2">
              <span className="section-label">{kpi.label}</span>
              <kpi.icon className="w-4 h-4 text-muted-foreground" />
            </div>
            <p className="text-2xl font-bold font-mono tracking-tight">
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : kpi.value}
            </p>
            <div className="flex items-center gap-1 mt-1">
              <span className={`status-dot ${kpi.up ? "status-dot-success" : "status-dot-danger"}`} />
              <span className={`text-xs font-medium ${kpi.up ? "text-success" : "text-danger"}`}>
                {kpi.change}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Main content: Chart + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Trend Over Time Chart */}
        <div className="lg:col-span-8 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold">Trend Volume Over Time</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Monthly data points by platform
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs flex-wrap">
              {platforms.map((p) => (
                <span key={p} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-0.5 rounded"
                    style={{ backgroundColor: PLATFORM_COLORS[p] || "oklch(0.6 0.1 200)" }}
                  />
                  {p}
                </span>
              ))}
            </div>
          </div>
          <div className="h-64">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 11 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 4,
                      border: "1px solid oklch(0.91 0.005 260)",
                    }}
                  />
                  {platforms.map((p) => (
                    <Line
                      key={p}
                      type="monotone"
                      dataKey={p}
                      stroke={PLATFORM_COLORS[p] || "oklch(0.6 0.1 200)"}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                {isLoading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  "No trend data available. Run a scrape to populate."
                )}
              </div>
            )}
          </div>
        </div>

        {/* Top Trends Feed */}
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-3">Top Signals</h2>
          <div className="space-y-2.5">
            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : top.length > 0 ? (
              top.map((t, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 border-b border-border/50 last:border-0">
                  <span className="text-xs font-mono text-muted-foreground w-4">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{t.name}</p>
                    <p className="text-[10px] text-muted-foreground">{t.platform}</p>
                  </div>
                  <span className="text-xs font-mono font-semibold">
                    {typeof t.score === "number" ? t.score.toFixed(1) : t.score}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-muted-foreground py-4 text-center">
                No trends yet. Run a scrape to get started.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Bottom panels: Top Trends Table + Momentum */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Top Trends Table */}
        <div className="lg:col-span-7 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">Trend Details</h2>
            <span className="section-label">{trends.length} records</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Topic</th>
                  <th className="text-left py-2 text-xs font-medium text-muted-foreground">Platform</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Virality</th>
                  <th className="text-right py-2 text-xs font-medium text-muted-foreground">Geo</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto text-muted-foreground" />
                    </td>
                  </tr>
                ) : top.length > 0 ? (
                  top.map((trend, i) => (
                    <tr
                      key={i}
                      className="border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="py-2.5 font-medium text-xs">{trend.name}</td>
                      <td className="py-2.5 text-muted-foreground text-xs">{trend.platform}</td>
                      <td className="py-2.5 text-right font-mono font-medium text-xs">
                        {typeof trend.score === "number" ? trend.score.toFixed(1) : trend.score}
                      </td>
                      <td className="py-2.5 text-right text-xs text-muted-foreground">{trend.geo}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-xs text-muted-foreground">
                      No data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Momentum Score */}
        <div className="lg:col-span-5 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold">Weekly Momentum</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                New trend entries per week
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-warning" />
              <span className="text-lg font-bold font-mono">{latestMomentum}</span>
            </div>
          </div>
          <div className="h-40">
            {momentumData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={momentumData}>
                  <defs>
                    <linearGradient id="momentumGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.50 0.20 260)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.50 0.20 260)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="oklch(0.50 0.20 260)"
                    strokeWidth={2}
                    fill="url(#momentumGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No momentum data yet"}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
