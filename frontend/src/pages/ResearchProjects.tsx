/*
 * Research Projects — Workspace page
 * Design: Header with create button → Grid of project cards with status indicators
 */
import {
  FolderKanban,
  Plus,
  Clock,
  Users,
  MoreHorizontal,
  ArrowUpRight,
  CheckCircle2,
  CircleDot,
  PauseCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

const PROJECTS = [
  {
    name: "AI Agent Market Analysis",
    description: "Deep-dive into the autonomous AI agent ecosystem, key players, and market sizing.",
    status: "active" as const,
    topics: 24,
    sources: 5,
    lastUpdated: "2h ago",
    progress: 72,
    team: ["MC", "AB"],
  },
  {
    name: "Sustainable Packaging Trends",
    description: "Tracking consumer demand shifts toward eco-friendly packaging solutions.",
    status: "active" as const,
    topics: 18,
    sources: 4,
    lastUpdated: "1d ago",
    progress: 45,
    team: ["MC"],
  },
  {
    name: "Crypto Sentiment Tracker",
    description: "Real-time sentiment analysis across Reddit, Twitter, and news for top 20 tokens.",
    status: "paused" as const,
    topics: 32,
    sources: 3,
    lastUpdated: "5d ago",
    progress: 88,
    team: ["MC", "JD", "KL"],
  },
  {
    name: "Health & Longevity Report",
    description: "Quarterly report on emerging health trends, supplements, and longevity research.",
    status: "completed" as const,
    topics: 15,
    sources: 5,
    lastUpdated: "2w ago",
    progress: 100,
    team: ["AB"],
  },
  {
    name: "Creator Economy Deep Dive",
    description: "Analyzing the shift from traditional media to creator-led platforms and monetization.",
    status: "active" as const,
    topics: 21,
    sources: 4,
    lastUpdated: "3h ago",
    progress: 35,
    team: ["MC", "AB"],
  },
  {
    name: "Edge Computing Landscape",
    description: "Mapping the edge computing market: providers, use cases, and adoption curves.",
    status: "active" as const,
    topics: 12,
    sources: 3,
    lastUpdated: "6h ago",
    progress: 58,
    team: ["JD"],
  },
];

const STATUS_CONFIG = {
  active: { icon: CircleDot, label: "Active", color: "text-success", dot: "status-dot-success" },
  paused: { icon: PauseCircle, label: "Paused", color: "text-warning", dot: "status-dot-warning" },
  completed: { icon: CheckCircle2, label: "Completed", color: "text-primary", dot: "bg-primary" },
};

export default function ResearchProjects() {
  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Research Projects</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Organize your trend research into focused projects with tracked progress.
          </p>
        </div>
        <Button size="sm" className="h-8 text-xs gap-1.5" onClick={() => toast("Feature coming soon")}>
          <Plus className="w-3.5 h-3.5" /> New Project
        </Button>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-6 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="status-dot status-dot-success" />
          <span className="font-medium">4 Active</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="status-dot status-dot-warning" />
          <span className="font-medium">1 Paused</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="status-dot bg-primary" />
          <span className="font-medium">1 Completed</span>
        </span>
      </div>

      {/* Project grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {PROJECTS.map((project, i) => {
          const status = STATUS_CONFIG[project.status];
          return (
            <div
              key={i}
              className="bg-card border border-border p-4 hover:border-primary/30 transition-colors group"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <FolderKanban className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold group-hover:text-primary transition-colors">
                    {project.name}
                  </h3>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="p-1 hover:bg-muted rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      <MoreHorizontal className="w-4 h-4 text-muted-foreground" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Open</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Edit</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => toast("Feature coming soon")}>Archive</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              {/* Description */}
              <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                {project.description}
              </p>

              {/* Status + meta */}
              <div className="flex items-center gap-3 mb-3 text-xs">
                <span className={`flex items-center gap-1 ${status.color}`}>
                  <span className={`status-dot ${status.dot}`} />
                  {status.label}
                </span>
                <span className="text-muted-foreground">{project.topics} topics</span>
                <span className="text-muted-foreground">{project.sources} sources</span>
              </div>

              {/* Progress bar */}
              <div className="mb-3">
                <div className="flex items-center justify-between text-[10px] mb-1">
                  <span className="text-muted-foreground uppercase tracking-wider">Progress</span>
                  <span className="font-mono font-medium">{project.progress}%</span>
                </div>
                <div className="h-1 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all"
                    style={{ width: `${project.progress}%` }}
                  />
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  {project.team.map((initials, j) => (
                    <div
                      key={j}
                      className="w-5 h-5 rounded-full bg-muted flex items-center justify-center text-[9px] font-semibold text-muted-foreground"
                    >
                      {initials}
                    </div>
                  ))}
                </div>
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  {project.lastUpdated}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
