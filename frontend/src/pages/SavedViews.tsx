/*
 * Saved Views — Bookmarked filter configurations and trend snapshots
 */
import {
  Bookmark,
  Plus,
  Clock,
  Filter,
  MoreHorizontal,
  ArrowUpRight,
  Trash2,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

const SAVED_VIEWS = [
  {
    name: "AI Agents — Global, All Sources",
    filters: { keyword: "AI Agents", region: "Global", source: "All", timeframe: "30d" },
    lastRun: "2h ago",
    results: 847,
    pinned: true,
  },
  {
    name: "Sustainable Packaging — US Only",
    filters: { keyword: "Sustainable Packaging", region: "US", source: "Google Trends", timeframe: "90d" },
    lastRun: "1d ago",
    results: 312,
    pinned: true,
  },
  {
    name: "Crypto Sentiment — Reddit + HN",
    filters: { keyword: "Cryptocurrency", region: "Global", source: "Reddit, HN", timeframe: "7d" },
    lastRun: "5d ago",
    results: 1204,
    pinned: false,
  },
  {
    name: "Health Trends — YouTube Focus",
    filters: { keyword: "Longevity", region: "Global", source: "YouTube", timeframe: "30d" },
    lastRun: "3d ago",
    results: 156,
    pinned: false,
  },
  {
    name: "Edge Computing — Asia Pacific",
    filters: { keyword: "Edge Computing", region: "APAC", source: "All", timeframe: "90d" },
    lastRun: "1w ago",
    results: 89,
    pinned: false,
  },
];

export default function SavedViews() {
  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Saved Views</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Quick-access bookmarks for your most-used filter configurations.
          </p>
        </div>
        <Button size="sm" className="h-8 text-xs gap-1.5" onClick={() => toast("Feature coming soon")}>
          <Plus className="w-3.5 h-3.5" /> Save Current View
        </Button>
      </div>

      {/* Views grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {SAVED_VIEWS.map((view, i) => (
          <div
            key={i}
            className="bg-card border border-border p-4 hover:border-primary/30 transition-colors group"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <Bookmark className={`w-4 h-4 ${view.pinned ? "text-primary fill-primary" : "text-muted-foreground"}`} />
                <h3 className="text-sm font-semibold">{view.name}</h3>
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="p-1 hover:bg-muted rounded opacity-0 group-hover:opacity-100 transition-opacity">
                    <MoreHorizontal className="w-4 h-4 text-muted-foreground" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Run Now</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Edit Filters</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => toast("Feature coming soon")}>
                    {view.pinned ? "Unpin" : "Pin"}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => toast("Feature coming soon")} className="text-destructive">
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Filter tags */}
            <div className="flex flex-wrap gap-1.5 mb-3">
              {Object.entries(view.filters).map(([key, val]) => (
                <span
                  key={key}
                  className="text-[10px] px-1.5 py-0.5 bg-muted text-muted-foreground flex items-center gap-1"
                >
                  <Filter className="w-2.5 h-2.5" />
                  {val}
                </span>
              ))}
            </div>

            {/* Stats */}
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  {view.lastRun}
                </span>
                <span className="font-mono font-medium">{view.results.toLocaleString()} results</span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[10px] gap-1 px-2"
                onClick={() => toast("Feature coming soon")}
              >
                <Play className="w-3 h-3" /> Run
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
