import { Loader2, Sparkles } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendRow } from "@/lib/api";

type TrendChartPoint = {
  date: string;
  [key: string]: string | number | undefined;
};

interface TrendExplorerChartPanelProps {
  loading: boolean;
  selectedNiche: string;
  chartData: TrendChartPoint[];
  topKeywords: string[];
  trends: TrendRow[];
  colors: string[];
}

export default function TrendExplorerChartPanel({
  loading,
  selectedNiche,
  chartData,
  topKeywords,
  trends,
  colors,
}: TrendExplorerChartPanelProps) {
  const keywordRows = topKeywords.map((keyword) => {
    const rows = trends.filter((row) => row.keyword === keyword);
    const count = rows.length;
    const avgScore = rows.reduce((sum, row) => sum + (row.virality_score ?? 0), 0) / (count || 1);
    return { keyword, count, avgScore };
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      <div className="lg:col-span-8 bg-card border border-border p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold">Trend Over Time</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {selectedNiche !== "all-niches" ? `Niche: ${selectedNiche}` : "All niches"} - top keywords by virality
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
                {topKeywords.map((keyword, index) => (
                  <Line
                    key={keyword}
                    type="monotone"
                    dataKey={keyword}
                    stroke={colors[index % colors.length]}
                    strokeWidth={index === 0 ? 2.5 : 1.5}
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
            {topKeywords.map((keyword, index) => (
              <span key={keyword} className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 rounded" style={{ background: colors[index % colors.length] }} />
                {keyword.slice(0, 25)}
              </span>
            ))}
          </div>
        )}
      </div>

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
            {keywordRows.map(({ keyword, count, avgScore }, index) => (
              <div key={keyword} className="flex items-center gap-2 text-xs">
                <span className="w-4 font-mono text-muted-foreground">{index + 1}</span>
                <span className="flex-1 truncate font-medium">{keyword}</span>
                <span className="font-mono text-primary">{avgScore.toFixed(1)}</span>
                <span className="text-muted-foreground">{count}x</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground text-center py-4">
            No keywords found. Run a scrape to populate data.
          </p>
        )}
      </div>
    </div>
  );
}
