import { Clock, Loader2, MousePointerClick } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type ChartDatum = {
  name: string;
  value: number;
};

const PERF_COLORS: Record<string, string> = {
  winning: "oklch(0.65 0.17 165)",
  optimized: "oklch(0.50 0.20 260)",
  scaling: "oklch(0.72 0.17 70)",
  growing: "oklch(0.60 0.22 25)",
  testing: "oklch(0.55 0.015 260)",
  unknown: "oklch(0.75 0.01 260)",
};

const PIE_COLORS = [
  "oklch(0.50 0.20 260)",
  "oklch(0.65 0.17 165)",
  "oklch(0.72 0.17 70)",
  "oklch(0.55 0.18 300)",
  "oklch(0.60 0.22 25)",
  "oklch(0.60 0.22 340)",
  "oklch(0.55 0.25 320)",
  "oklch(0.65 0.15 170)",
  "oklch(0.45 0.15 200)",
  "oklch(0.70 0.12 100)",
];

const PLATFORM_COLORS_ADS: Record<string, string> = {
  Facebook: "oklch(0.50 0.20 260)",
  Instagram: "oklch(0.60 0.22 340)",
  Messenger: "oklch(0.55 0.18 300)",
  Threads: "oklch(0.55 0.25 320)",
  "Audience_network": "oklch(0.65 0.15 170)",
};

function renderCustomPieLabel({
  cx,
  cy,
  midAngle,
  outerRadius,
  name,
  percent,
}: {
  cx: number;
  cy: number;
  midAngle: number;
  outerRadius: number;
  name: string;
  percent: number;
}) {
  if (percent < 0.03) return null;
  const radian = Math.PI / 180;
  const radius = outerRadius + 22;
  const x = cx + radius * Math.cos(-midAngle * radian);
  const y = cy + radius * Math.sin(-midAngle * radian);
  return (
    <text
      x={x}
      y={y}
      fill="oklch(0.45 0.015 260)"
      textAnchor={x > cx ? "start" : "end"}
      dominantBaseline="central"
      fontSize={10}
      fontWeight={500}
    >
      {name} {(percent * 100).toFixed(0)}%
    </text>
  );
}

interface DashboardAdsChartsProps {
  adsLoading: boolean;
  perfDist: ChartDatum[];
  platformBreakdown: ChartDatum[];
  formatBreakdown: ChartDatum[];
  ctaDist: ChartDatum[];
  daysActiveDist: ChartDatum[];
}

export default function DashboardAdsCharts({
  adsLoading,
  perfDist,
  platformBreakdown,
  formatBreakdown,
  ctaDist,
  daysActiveDist,
}: DashboardAdsChartsProps) {
  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Performance Distribution</h2>
          <p className="text-xs text-muted-foreground mb-3">Ads by performance tier</p>
          <div className="h-52">
            {perfDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={perfDist} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" width={70} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                    {perfDist.map((entry, index) => (
                      <Cell
                        key={`${entry.name}-${index}`}
                        fill={PERF_COLORS[entry.name.toLowerCase()] || PIE_COLORS[index % PIE_COLORS.length]}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Ads by Platform</h2>
          <p className="text-xs text-muted-foreground mb-3">Individual platform presence across ads</p>
          <div className="h-52">
            {platformBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={platformBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={35}
                    outerRadius={65}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={renderCustomPieLabel}
                    labelLine
                  >
                    {platformBreakdown.map((entry, index) => (
                      <Cell
                        key={`${entry.name}-${index}`}
                        fill={PLATFORM_COLORS_ADS[entry.name] || PIE_COLORS[index % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 4 }}
                    formatter={(value: number, name: string) => [`${value} ads`, name]}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-4 bg-card border border-border p-4">
          <h2 className="text-sm font-semibold mb-1">Ad Formats</h2>
          <p className="text-xs text-muted-foreground mb-3">Creative format distribution</p>
          <div className="h-52">
            {formatBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={formatBreakdown}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                    {formatBreakdown.map((entry, index) => (
                      <Cell key={`${entry.name}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-6 bg-card border border-border p-4">
          <div className="flex items-center gap-2 mb-1">
            <MousePointerClick className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">CTA Type Breakdown</h2>
          </div>
          <p className="text-xs text-muted-foreground mb-3">Call-to-action distribution across ads</p>
          <div className="h-52">
            {ctaDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={ctaDist} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 9 }} stroke="oklch(0.55 0.015 260)" width={90} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                    {ctaDist.map((entry, index) => (
                      <Cell key={`${entry.name}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-6 bg-card border border-border p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Ad Longevity</h2>
          </div>
          <p className="text-xs text-muted-foreground mb-3">Distribution of how long ads have been running</p>
          <div className="h-52">
            {daysActiveDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={daysActiveDist}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.91 0.005 260)" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <YAxis tick={{ fontSize: 10 }} stroke="oklch(0.55 0.015 260)" />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                    {daysActiveDist.map((entry, index) => (
                      <Cell key={`${entry.name}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                {adsLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : "No ads data yet"}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
