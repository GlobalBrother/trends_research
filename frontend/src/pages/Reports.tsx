/*
 * Reports — Generated intelligence reports
 * Design: Header with generate button → Report list with status badges
 */
import {
  FileBarChart,
  Plus,
  Download,
  Eye,
  Clock,
  CheckCircle2,
  Loader2,
  FileText,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

const REPORTS = [
  {
    title: "Q1 2026 Trend Intelligence Brief",
    type: "Quarterly Report",
    status: "ready" as const,
    pages: 24,
    generated: "Mar 15, 2026",
    topics: ["AI Agents", "Edge Computing", "Sustainability"],
  },
  {
    title: "AI Agent Ecosystem Deep Dive",
    type: "Topic Report",
    status: "ready" as const,
    pages: 18,
    generated: "Mar 12, 2026",
    topics: ["AI Agents", "LLM Frameworks", "Automation"],
  },
  {
    title: "Weekly Trend Digest — Week 11",
    type: "Weekly Digest",
    status: "generating" as const,
    pages: null,
    generated: "Generating…",
    topics: ["All Topics"],
  },
  {
    title: "Sustainable Packaging Market Report",
    type: "Topic Report",
    status: "ready" as const,
    pages: 15,
    generated: "Mar 8, 2026",
    topics: ["Sustainable Packaging", "Consumer Trends"],
  },
  {
    title: "Crypto Sentiment Analysis — February",
    type: "Monthly Report",
    status: "ready" as const,
    pages: 12,
    generated: "Mar 1, 2026",
    topics: ["Cryptocurrency", "Sentiment"],
  },
  {
    title: "Health & Longevity Trends Q4 2025",
    type: "Quarterly Report",
    status: "ready" as const,
    pages: 20,
    generated: "Jan 5, 2026",
    topics: ["Health", "Longevity", "Supplements"],
  },
];

const STATUS_MAP = {
  ready: { label: "Ready", icon: CheckCircle2, color: "text-success bg-success/10" },
  generating: { label: "Generating", icon: Loader2, color: "text-primary bg-primary/10" },
};

export default function Reports() {
  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Reports</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Auto-generated intelligence reports and trend digests.
          </p>
        </div>
        <Button size="sm" className="h-8 text-xs gap-1.5" onClick={() => toast("Feature coming soon")}>
          <Plus className="w-3.5 h-3.5" /> Generate Report
        </Button>
      </div>

      {/* Report list */}
      <div className="bg-card border border-border">
        {/* Table header */}
        <div className="grid grid-cols-12 gap-4 px-4 py-2.5 border-b border-border text-xs font-medium text-muted-foreground uppercase tracking-wider">
          <div className="col-span-5">Report</div>
          <div className="col-span-2">Type</div>
          <div className="col-span-1">Status</div>
          <div className="col-span-1 text-right">Pages</div>
          <div className="col-span-2">Generated</div>
          <div className="col-span-1"></div>
        </div>

        {/* Rows */}
        {REPORTS.map((report, i) => {
          const status = STATUS_MAP[report.status];
          return (
            <div
              key={i}
              className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors items-center"
            >
              <div className="col-span-5 flex items-center gap-3">
                <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                <div>
                  <p className="text-sm font-medium">{report.title}</p>
                  <div className="flex gap-1.5 mt-1">
                    {report.topics.map((t, j) => (
                      <span
                        key={j}
                        className="text-[10px] px-1.5 py-0.5 bg-muted text-muted-foreground"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="col-span-2 text-xs text-muted-foreground">{report.type}</div>
              <div className="col-span-1">
                <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-sm ${status.color}`}>
                  <status.icon className={`w-3 h-3 ${report.status === "generating" ? "animate-spin" : ""}`} />
                  {status.label}
                </span>
              </div>
              <div className="col-span-1 text-right text-xs font-mono text-muted-foreground">
                {report.pages ?? "—"}
              </div>
              <div className="col-span-2 text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {report.generated}
              </div>
              <div className="col-span-1 flex items-center justify-end gap-1">
                {report.status === "ready" && (
                  <>
                    <button
                      className="p-1 hover:bg-muted rounded transition-colors"
                      onClick={() => toast("Feature coming soon")}
                    >
                      <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                    <button
                      className="p-1 hover:bg-muted rounded transition-colors"
                      onClick={() => toast("Feature coming soon")}
                    >
                      <Download className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                  </>
                )}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="p-1 hover:bg-muted rounded transition-colors">
                      <MoreHorizontal className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>View</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Download PDF</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Share</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Delete</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
