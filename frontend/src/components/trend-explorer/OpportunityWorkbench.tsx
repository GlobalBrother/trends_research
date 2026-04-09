import { useEffect, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useApi, useLazyApi } from "@/hooks/useApi";
import {
  getCluster,
  getClusterAds,
  getClusters,
  submitClusterFeedback,
  type ClusterAdMatch,
  type ClusterDetail,
  type ClusterRow,
} from "@/lib/api";

interface OpportunityWorkbenchProps {
  selectedGeo: string;
}

export default function OpportunityWorkbench({
  selectedGeo,
}: OpportunityWorkbenchProps) {
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
                    {cluster.ad_opportunity_score?.toFixed(1) ?? "-"}
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
                  <div>Opportunity: <span className="font-mono">{detail.insight?.ad_opportunity_score?.toFixed(1) ?? "-"}</span></div>
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
                  <p className="font-medium mt-1">{detail.insight?.saturation_risk?.toFixed(1) ?? "-"}</p>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-muted-foreground">Safety Risk</p>
                  <p className="font-medium mt-1">{detail.insight?.brand_safety_risk?.toFixed(1) ?? "-"}</p>
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
                          {ad.brand_name || "Unknown brand"} - {ad.display_format || "Unknown format"} - {ad.cta_type || "No CTA"}
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
                  {detail.feedback_summary.avg_rating != null ? ` - Avg ${detail.feedback_summary.avg_rating.toFixed(1)}` : ""}
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
