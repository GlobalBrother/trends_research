/*
 * DashboardLayout — Tactical Intelligence Grid
 * Design: 240px navy sidebar | 56px top bar | fluid content area
 * Sidebar: deep navy (#0F172A), icon + label nav, grouped sections
 * Top bar: white, global search, date range, user menu
 */
import { useState, useMemo, type ReactNode } from "react";
import { LogOut } from "lucide-react";
import { Link, useLocation } from "wouter";
import {
  LayoutDashboard,
  Compass,
  FolderKanban,
  FileBarChart,
  Bookmark,
  Bell,
  Settings,
  Search,
  ChevronDown,
  Menu,
  X,
  TrendingUp,
  Megaphone,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { isAdmin } from "@/lib/api";

interface NavItem {
  href: string;
  icon: typeof LayoutDashboard;
  label: string;
  adminOnly?: boolean;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "OVERVIEW",
    items: [
      { href: "/", icon: LayoutDashboard, label: "Dashboard" },
      { href: "/explorer", icon: Compass, label: "Trend Explorer" },
    ],
  },
  {
    label: "WORKSPACE",
    items: [
      { href: "/projects", icon: FolderKanban, label: "Research Projects" },
      { href: "/reports", icon: FileBarChart, label: "Reports" },
      { href: "/saved", icon: Bookmark, label: "Saved Views" },
    ],
  },
  {
    label: "ADVERTISING",
    items: [
      { href: "/my-ads", icon: Megaphone, label: "My Ads" },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { href: "/alerts", icon: Bell, label: "Alerts" },
      { href: "/settings", icon: Settings, label: "Settings", adminOnly: true },
    ],
  },
];

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const [location] = useLocation();
  const userIsAdmin = useMemo(() => isAdmin(), []);

  return (
    <nav className="flex flex-col gap-6 px-3 py-4 sidebar-scroll overflow-y-auto flex-1">
      {NAV_SECTIONS.map((section) => {
        // Filter out admin-only items for non-admin users
        const visibleItems = section.items.filter(
          (item) => !item.adminOnly || userIsAdmin
        );
        // Don't render the section if no visible items
        if (visibleItems.length === 0) return null;

        return (
          <div key={section.label}>
            <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-sidebar-foreground/40">
              {section.label}
            </p>
            <div className="flex flex-col gap-0.5">
              {visibleItems.map((item) => {
                const isActive = location === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    className={`flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                      isActive
                        ? "bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-sidebar-primary"
                        : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/50 border-l-2 border-transparent"
                    }`}
                  >
                    <item.icon className="w-4 h-4 shrink-0" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const authEmail = useMemo(() => localStorage.getItem("auth_email") || "user@company.com", []);
  const authInitials = useMemo(() => {
    const parts = authEmail.split("@")[0].split(/[._-]/);
    return parts.length >= 2
      ? (parts[0][0] + parts[1][0]).toUpperCase()
      : authEmail.slice(0, 2).toUpperCase();
  }, [authEmail]);
  const authName = useMemo(() => {
    const parts = authEmail.split("@")[0].split(/[._-]/);
    return parts.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
  }, [authEmail]);

  const handleLogout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_email");
    localStorage.removeItem("auth_role");
    window.location.href = "/login";
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar — Desktop */}
      <aside className="hidden lg:flex flex-col w-60 bg-sidebar text-sidebar-foreground border-r border-sidebar-border shrink-0">
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-5 h-14 border-b border-sidebar-border shrink-0">
          <div className="w-7 h-7 bg-sidebar-primary rounded flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-sidebar-primary-foreground" />
          </div>
          <span className="text-sm font-semibold text-sidebar-foreground tracking-tight">
            Trends Research
          </span>
        </div>
        <SidebarNav />
        {/* Sidebar footer */}
        <div className="px-5 py-3 border-t border-sidebar-border shrink-0">
          <p className="text-[10px] text-sidebar-foreground/30 uppercase tracking-wider">
            v2.0 &middot; Intelligence Platform
          </p>
        </div>
      </aside>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative w-60 h-full bg-sidebar text-sidebar-foreground flex flex-col">
            <div className="flex items-center justify-between px-5 h-14 border-b border-sidebar-border">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 bg-sidebar-primary rounded flex items-center justify-center">
                  <TrendingUp className="w-4 h-4 text-sidebar-primary-foreground" />
                </div>
                <span className="text-sm font-semibold">Trends Research</span>
              </div>
              <button onClick={() => setMobileOpen(false)}>
                <X className="w-4 h-4 text-sidebar-foreground/60" />
              </button>
            </div>
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      {/* Main area */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Top header — 56px */}
        <header className="flex items-center justify-between h-14 px-4 lg:px-6 bg-card border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            {/* Mobile menu button */}
            <button
              className="lg:hidden p-1.5 hover:bg-muted rounded"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </button>
            {/* Global search */}
            <div className="relative hidden sm:block">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <Input
                placeholder="Search trends, topics, reports…"
                className="pl-8 w-64 h-8 text-sm bg-muted/50 border-0 focus-visible:ring-1"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Date range */}
            <Button
              variant="outline"
              size="sm"
              className="hidden md:flex h-8 text-xs gap-1.5 bg-transparent"
            >
              Last 30 days
              <ChevronDown className="w-3 h-3" />
            </Button>

            {/* Workspace selector */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="hidden md:flex h-8 text-xs gap-1.5 bg-transparent"
                >
                  Default Workspace
                  <ChevronDown className="w-3 h-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Default Workspace</DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => toast("Feature coming soon")}
                >
                  Marketing Team
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => toast("Feature coming soon")}
                >
                  Create Workspace
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Notifications */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 relative"
              onClick={() => toast("Feature coming soon")}
            >
              <Bell className="w-4 h-4" />
              <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-danger rounded-full" />
            </Button>

            {/* User menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 h-8 px-2 rounded hover:bg-muted transition-colors">
                  <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                    <span className="text-[10px] font-semibold text-primary-foreground">
                      {authInitials}
                    </span>
                  </div>
                  <ChevronDown className="w-3 h-3 text-muted-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <div className="px-2 py-1.5">
                  <p className="text-sm font-medium">{authName}</p>
                  <p className="text-xs text-muted-foreground">
                    {authEmail}
                  </p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => toast("Feature coming soon")}>
                  Profile
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => toast("Feature coming soon")}>
                  Preferences
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout}>
                  <LogOut className="w-3.5 h-3.5 mr-2" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Content area */}
        <main className="flex-1 overflow-y-auto bg-background">
          {children}
        </main>
      </div>
    </div>
  );
}
