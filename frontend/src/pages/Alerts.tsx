/*
 * Alerts — Notification rules and alert history
 */
import {
  Bell,
  Plus,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  MoreHorizontal,
  Zap,
  TrendingUp,
  ArrowUpRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

const ALERT_RULES = [
  {
    name: "Breakout Detection",
    description: "Notify when any tracked topic crosses the 90th percentile momentum score.",
    enabled: true,
    triggers: 12,
    lastTriggered: "2h ago",
    channel: "Email + Slack",
  },
  {
    name: "Sentiment Shift",
    description: "Alert when sentiment for a monitored topic drops below 40% positive.",
    enabled: true,
    triggers: 3,
    lastTriggered: "1d ago",
    channel: "Email",
  },
  {
    name: "New Competitor Entry",
    description: "Detect when a new player appears in tracked niche markets.",
    enabled: false,
    triggers: 0,
    lastTriggered: "Never",
    channel: "Slack",
  },
  {
    name: "Weekly Digest",
    description: "Automated weekly summary of all trend movements and anomalies.",
    enabled: true,
    triggers: 8,
    lastTriggered: "3d ago",
    channel: "Email",
  },
];

const RECENT_ALERTS = [
  {
    title: "AI Agents crossed 90th percentile",
    rule: "Breakout Detection",
    time: "2h ago",
    severity: "high" as const,
  },
  {
    title: "Crypto sentiment dropped to 38%",
    rule: "Sentiment Shift",
    time: "1d ago",
    severity: "warning" as const,
  },
  {
    title: "Weekly digest generated for Week 11",
    rule: "Weekly Digest",
    time: "3d ago",
    severity: "info" as const,
  },
  {
    title: "Edge Computing momentum spike detected",
    rule: "Breakout Detection",
    time: "4d ago",
    severity: "high" as const,
  },
  {
    title: "Sustainable Packaging sentiment stable",
    rule: "Sentiment Shift",
    time: "5d ago",
    severity: "info" as const,
  },
];

const SEVERITY_MAP = {
  high: { icon: Zap, color: "text-danger", bg: "bg-danger/10", dot: "status-dot-danger" },
  warning: { icon: AlertTriangle, color: "text-warning", bg: "bg-warning/10", dot: "status-dot-warning" },
  info: { icon: CheckCircle2, color: "text-primary", bg: "bg-primary/10", dot: "bg-primary" },
};

export default function Alerts() {
  return (
    <div className="p-4 lg:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Alerts</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Configure notification rules and review alert history.
          </p>
        </div>
        <Button size="sm" className="h-8 text-xs gap-1.5" onClick={() => toast("Feature coming soon")}>
          <Plus className="w-3.5 h-3.5" /> New Alert Rule
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Alert Rules */}
        <div className="lg:col-span-7 space-y-3">
          <h2 className="section-label">Alert Rules</h2>
          <div className="space-y-2">
            {ALERT_RULES.map((rule, i) => (
              <div
                key={i}
                className="bg-card border border-border p-4 flex items-start gap-4 group"
              >
                <div className="pt-0.5">
                  <Switch
                    checked={rule.enabled}
                    onCheckedChange={() => toast("Feature coming soon")}
                  />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold">{rule.name}</h3>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="p-1 hover:bg-muted rounded opacity-0 group-hover:opacity-100 transition-opacity">
                          <MoreHorizontal className="w-4 h-4 text-muted-foreground" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Edit</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Test</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => toast("Feature coming soon")} className="text-destructive">Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                    {rule.description}
                  </p>
                  <div className="flex items-center gap-4 mt-2 text-[10px] text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Zap className="w-3 h-3" />
                      {rule.triggers} triggers
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Last: {rule.lastTriggered}
                    </span>
                    <span className="flex items-center gap-1">
                      <Bell className="w-3 h-3" />
                      {rule.channel}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Alerts */}
        <div className="lg:col-span-5 space-y-3">
          <h2 className="section-label">Recent Notifications</h2>
          <div className="bg-card border border-border">
            {RECENT_ALERTS.map((alert, i) => {
              const sev = SEVERITY_MAP[alert.severity];
              return (
                <div
                  key={i}
                  className="flex items-start gap-3 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors"
                >
                  <div className={`p-1.5 rounded-sm ${sev.bg} mt-0.5`}>
                    <sev.icon className={`w-3 h-3 ${sev.color}`} />
                  </div>
                  <div className="flex-1">
                    <p className="text-xs font-medium">{alert.title}</p>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                      <span>{alert.rule}</span>
                      <span>&middot;</span>
                      <span>{alert.time}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
