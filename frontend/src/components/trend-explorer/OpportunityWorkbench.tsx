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
  selectedNiche: string;
}

export default function OpportunityWorkbench({
  selectedGeo,
  selectedNiche,
}: OpportunityWorkbenchProps) {
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null);
  const { data: clustersData, loading: clustersLoading, refetch: refetchClusters } = useApi(
    () => getClusters({ limit: 8, niche_name: selectedNiche }),
    [selectedGeo, selectedNiche]
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
                <div className="flex-1">
                  <h3 className="text-base font-semibold">{detail.title}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary font-mono rounded">
                      Score: {detail.insight?.ad_opportunity_score?.toFixed(1) ?? "-"}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded capitalize">{detail.lifecycle_stage}</span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-muted rounded">Conf {detail.confidence_score.toFixed(0)}</span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                   <p className="text-[10px] text-muted-foreground uppercase font-semibold">Opportunity Window</p>
                   <p className="text-xs font-medium">{detail.insight?.ad_timing_window || "Monitor Signal"}</p>
                </div>
              </div>

              {/* Explainable Scoring Section */}
              <div className="border border-border rounded-md p-3 bg-muted/30">
                <p className="text-xs font-semibold mb-2">Opportunity Analysis (Explainable Scoring)</p>
                <div className="space-y-3">
                  {detail.insight?.explanation?.components && Object.entries(detail.insight.explanation.components).map(([key, val]) => (
                    <div key={key} className="space-y-1">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="capitalize">{key.replace("_", " ")}</span>
                        <span className="font-mono font-medium">{val.toFixed(1)}</span>
                      </div>
                      <div className="w-full bg-border h-1 rounded-full overflow-hidden">
                        <div 
                          className="bg-primary h-full transition-all" 
                          style={{ width: `${Math.min(100, Math.max(0, val))}%` }}
                        />
                      </div>
                      {detail.insight?.explanation?.descriptions?.[key] && (
                        <p className="text-[10px] text-muted-foreground italic">
                          {detail.insight.explanation.descriptions[key]}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-border rounded-md p-3">
                  <p className="text-xs font-semibold mb-2">Audience Intent & Creative Angles</p>
                  <p className="text-[11px] text-muted-foreground mb-3 leading-relaxed">
                    {detail.insight?.audience_intent || "Audience signal is still forming across tracked sources."}
                  </p>
                  <div className="space-y-2">
                    {(detail.insight?.creative_angle_candidates ?? []).map((angle, idx) => (
                      <div key={idx} className="flex gap-2 text-[11px] text-muted-foreground">
                        <span className="text-primary">•</span>
                        <span>{angle}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-xs font-semibold mb-2">Platform Fit</p>
                  <div className="space-y-3">
                    {(detail.insight?.platform_fit ?? []).map((fit) => (
                      <div key={fit.platform} className="space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span>{fit.platform}</span>
                          <span className="font-mono text-primary font-medium">{fit.fit_score.toFixed(1)}</span>
                        </div>
                        <div className="w-full bg-border h-1 rounded-full overflow-hidden">
                          <div 
                            className="bg-primary/60 h-full transition-all" 
                            style={{ width: `${Math.min(100, Math.max(0, fit.fit_score))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Competitor Evidence Section */}
              <div className="border border-border rounded-md p-3 border-primary/20">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold">Competitor Evidence (Market Proof)</p>
                  <span className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary rounded">
                    {ads.length} Linked Ads
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {ads.length > 0 ? ads.map(({ match_score, ad }) => (
                    <div key={ad.id} className="flex items-center justify-between gap-3 text-xs p-2 rounded bg-muted/20 border border-border/50">
                      <div className="min-w-0">
                        <p className="font-medium truncate text-[11px]">{ad.title || ad.body || "Untitled Ad Signal"}</p>
                        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
                          <span className="font-semibold text-primary/80">{ad.brand_name || "Unidentified Brand"}</span>
                          <span>•</span>
                          <span>{ad.display_format || "Social Content"}</span>
                          <span>•</span>
                          <span>{ad.cta_type || "No CTA"}</span>
                        </div>
                      </div>
                      <div className="text-right">
                         <p className="text-[9px] text-muted-foreground uppercase font-bold">Match</p>
                         <p className="font-mono text-primary font-bold text-[11px]">{match_score.toFixed(1)}</p>
                      </div>
                    </div>
                  )) : (
                    <p className="text-[11px] text-muted-foreground py-2 text-center border border-dashed border-border rounded">
                      No direct ad matches found. This may be an untapped opportunity.
                    </p>
                  )}
                </div>
                {detail.insight?.explanation?.evidence?.brands?.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-2">
                    <span className="text-[10px] text-muted-foreground w-full">Top Competitors:</span>
                    {detail.insight.explanation.evidence.brands.map(([brand, count]) => (
                      <span key={brand} className="text-[10px] px-1.5 py-0.5 bg-muted rounded">
                        {brand} ({count})
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-border mt-auto">
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">
                  Analysis Feedback Loop
                </p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="h-7 text-[10px] px-3 font-bold uppercase" onClick={() => handleFeedback(true)} disabled={feedbackLoading}>
                    Useful
                  </Button>
                  <Button size="sm" variant="outline" className="h-7 text-[10px] px-3 font-bold uppercase" onClick={() => handleFeedback(false)} disabled={feedbackLoading}>
                    Not Useful
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="text-sm text-muted-foreground py-12 text-center flex flex-col items-center gap-3">
              <Search className="w-8 h-8 opacity-20" />
              <p>Select an opportunity to inspect the structured insight<br/>and competitor evidence.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
