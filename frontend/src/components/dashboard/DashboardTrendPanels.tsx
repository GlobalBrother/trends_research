import { Loader2, Zap } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type TrendPoint = {
  date: string;
  [key: string]: string | number | undefined;
};

type TrendSummary = {
  name: string;
  score: number | string;
  platform: string;
  geo: string;
};

type MomentumPoint = {
  date: string;
  score: number;
};

interface DashboardTrendPanelsProps {
  isLoading: boolean;
  chartData: TrendPoint[];
  platforms: string[];
  platformColors: Record<string, string>;
  top: TrendSummary[];
  momentumData: MomentumPoint[];
  latestMomentum: number;
}

export default function DashboardTrendPanels({
  isLoading,
  chartData,
  platforms,
  platformColors,
  top,
  momentumData,
  latestMomentum,
}: DashboardTrendPanelsProps) {
  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold">Trend Volume Over Time</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Monthly data points by platform
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs flex-wrap">
              {platforms.map((platform) => (
                <span key={platform} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-0.5 rounded"
                    style={{ backgroundColor: platformColors[platform] || "oklch(0.6 0.1 200)" }}
                  />
                  {platform}
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
                  {platforms.map((platform) => (
                    <Line
                      key={platform}
                      type="monotone"
                      dataKey={platform}
                      stroke={platformColors[platform] || "oklch(0.6 0.1 200)"}
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

        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-3">Top Signals</h2>
          <div className="space-y-2.5">
            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : top.length > 0 ? (
              top.map((signal, index) => (
                <div key={`${signal.name}-${index}`} className="flex items-center gap-3 py-1.5 border-b border-border/50 last:border-0">
                  <span className="text-xs font-mono text-muted-foreground w-4">{index + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{signal.name}</p>
                    <p className="text-[10px] text-muted-foreground">{signal.platform}</p>
                  </div>
                  <span className="text-xs font-mono font-semibold">
                    {typeof signal.score === "number" ? signal.score.toFixed(1) : signal.score}
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

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 bg-card border border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">Trend Details</h2>
            <span className="section-label">{top.length} records</span>
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
                  top.map((trend, index) => (
                    <tr
                      key={`${trend.name}-${index}`}
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
    </>
  );
}
