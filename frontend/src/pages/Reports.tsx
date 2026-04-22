import { FileBarChart, RefreshCw, Loader2, FileText, Clock, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApi, useLazyApi } from "@/hooks/useApi";
import { generateReports, getBacktests, getGeneratedReports, type BacktestRun, type GeneratedReport } from "@/lib/api";
import { toast } from "sonner";

function formatReportType(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function Reports() {
  const { data: reportsData, loading: reportsLoading, refetch: refetchReports } = useApi(
    () => getGeneratedReports(),
    []
  );
  const { data: backtestsData, loading: backtestsLoading, refetch: refetchBacktests } = useApi(
    () => getBacktests(),
    []
  );
  const { loading: generating, execute: doGenerate } = useLazyApi(generateReports);

  const reports: GeneratedReport[] = reportsData?.data ?? [];
  const backtests: BacktestRun[] = backtestsData?.data ?? [];

  const handleGenerate = async () => {
    try {
      await doGenerate();
      toast.success("Reports regenerated");
      refetchReports();
      refetchBacktests();
    } catch {
      toast.error("Failed to generate reports");
    }
  };

  return (
    <div className="p-4 lg:p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Reports</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Generated briefs backed by deterministic cluster insights and weekly backtests.
          </p>
        </div>
        <Button size="sm" className="h-8 text-xs gap-1.5" onClick={handleGenerate} disabled={generating}>
          {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Generate Briefs
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 bg-card border border-border">
          <div className="grid grid-cols-12 gap-4 px-4 py-2.5 border-b border-border text-xs font-medium text-muted-foreground uppercase tracking-wider">
            <div className="col-span-4">Report</div>
            <div className="col-span-2">Type</div>
            <div className="col-span-2">Cluster</div>
            <div className="col-span-2">Created</div>
            <div className="col-span-2">Summary</div>
          </div>
          {reportsLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading generated reports...
            </div>
          ) : reports.length > 0 ? (
            reports.map((report) => {
              const content = report.content as { clusters?: { title?: string }[]; recommended_actions?: { title?: string }[]; audience_intent?: string };
              const summary =
                content.audience_intent ||
                content.clusters?.[0]?.title ||
                content.recommended_actions?.[0]?.title ||
                "Structured brief ready";
              return (
                <div
                  key={report.id}
                  className="grid grid-cols-12 gap-4 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-muted/30 transition-colors items-center"
                >
                  <div className="col-span-4 flex items-center gap-3">
                    <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div>
                      <p className="text-sm font-medium">{report.title}</p>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        {Array.isArray((content as { clusters?: unknown[] }).clusters)
                          ? `${(content as { clusters?: unknown[] }).clusters?.length ?? 0} clusters included`
                          : "Single-brief output"}
                      </p>
                    </div>
                  </div>
                  <div className="col-span-2 text-xs text-muted-foreground">{formatReportType(report.report_type)}</div>
                  <div className="col-span-2 text-xs text-muted-foreground">{report.cluster_id ?? "Mixed"}</div>
                  <div className="col-span-2 text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {report.created_at ? new Date(report.created_at).toLocaleString() : "—"}
                  </div>
                  <div className="col-span-2 text-xs">{summary}</div>
                </div>
              );
            })
          ) : (
            <div className="text-center py-12 text-sm text-muted-foreground">
              No generated reports yet. Run the report generator to build a weekly digest, deep dive, and planning brief.
            </div>
          )}
        </div>

        <div className="lg:col-span-4 bg-card border border-border p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold">Backtesting</h2>
          </div>
          {backtestsLoading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading backtests...
            </div>
          ) : backtests.length > 0 ? (
            <div className="space-y-3">
              {backtests.slice(0, 5).map((run) => (
                <div key={run.id} className="border border-border rounded-md p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold">{run.run_label}</p>
                    <span className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary rounded">
                      {run.avg_opportunity_score.toFixed(1)}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-muted-foreground">
                    <div>
                      <p>Precision</p>
                      <p className="font-mono text-foreground mt-1">{run.precision_proxy.toFixed(1)}</p>
                    </div>
                    <div>
                      <p>Recall</p>
                      <p className="font-mono text-foreground mt-1">{run.recall_proxy.toFixed(1)}</p>
                    </div>
                    <div>
                      <p>Clusters</p>
                      <p className="font-mono text-foreground mt-1">{run.total_clusters}</p>
                    </div>
                    <div>
                      <p>Matched</p>
                      <p className="font-mono text-foreground mt-1">{run.matched_clusters}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground py-6">
              No backtesting runs recorded yet. Generating reports will also materialize a new weekly backtest snapshot.
            </div>
          )}

          <div className="border border-border rounded-md p-4">
            <div className="flex items-center gap-2 mb-2">
              <FileBarChart className="w-4 h-4 text-muted-foreground" />
              <p className="text-sm font-semibold">What ships in each brief</p>
            </div>
            <div className="space-y-2 text-xs text-muted-foreground">
              <p>`weekly_digest`: ranked cluster list with stage and confidence.</p>
              <p>`deep_dive`: one opportunity explained with timing, audience intent, and creative angles.</p>
              <p>`planning_brief`: concrete actions to test next in paid media.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
