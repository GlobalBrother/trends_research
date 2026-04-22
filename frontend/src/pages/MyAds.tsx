/**
 * My Ads — Track your own brand's ads via GetHooked
 * Features: Brand search & tracking, ads table with filters, performance charts
 */
import { useMemo, useState, useCallback, useEffect } from "react";
import {
  Megaphone,
  Search,
  Plus,
  Trash2,
  RefreshCw,
  Loader2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Eye,
  Target,
  Clock,
  Calendar,
  Filter,
  X,
  Building2,
  TrendingUp,
  BarChart3,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { useApi } from "@/hooks/useApi";
import { useFilters } from "@/contexts/FilterContext";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getMyBrands,
  getMyBrandAds,
  addMyBrand,
  removeMyBrand,
  refreshMyBrandAds,
  searchBrands,
  type AdsInsightRow,
  type MyBrandRow,
  type MyBrandAdsParams,
} from "@/lib/api";
import { toast } from "sonner";

/* ── constants ──────────────────────────────────────────────────────────── */

const PIE_COLORS = [
  "#6366f1", "#22d3ee", "#f59e0b", "#ef4444", "#10b981",
  "#8b5cf6", "#f97316", "#06b6d4", "#ec4899", "#84cc16",
];

const PAGE_SIZES = ["50", "100", "250", "500"];

/* ── helpers ─────────────────────────────────────────────────────────────── */

function parsePlatforms(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/* ── component ──────────────────────────────────────────────────────────── */

export default function MyAds() {
  const { geo } = useFilters();
  /* ── Brand search state ─────────────────────────────────────────────── */
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<
    { external_id: string; name: string; logo_url?: string; active_ads?: number }[]
  >([]);
  const [searching, setSearching] = useState(false);
  const [addingBrand, setAddingBrand] = useState<string | null>(null);

  /* ── Ads filter state ───────────────────────────────────────────────── */
  const [pageSize, setPageSize] = useState("100");
  const [offset, setOffset] = useState(0);
  const [brandFilter, setBrandFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [sortBy, setSortBy] = useState("start_date");
  const [sortDir, setSortDir] = useState("desc");

  /* ── Build params ───────────────────────────────────────────────────── */
  const adsParams: MyBrandAdsParams = useMemo(() => {
    const p: MyBrandAdsParams = {
      limit: Number(pageSize),
      offset,
      sort_by: sortBy,
      sort_dir: sortDir,
      geo,
    };
    if (brandFilter) p.brand_name = brandFilter;
    if (dateFrom) p.date_from = dateFrom;
    if (dateTo) p.date_to = dateTo;
    if (platformFilter) p.platform_filter = platformFilter;
    return p;
  }, [pageSize, offset, brandFilter, dateFrom, dateTo, platformFilter, sortBy, sortDir]);

  /* ── Data fetching ──────────────────────────────────────────────────── */
  const {
    data: brandsData,
    loading: brandsLoading,
    refetch: refetchBrands,
  } = useApi(() => getMyBrands(), []);

  const {
    data: adsData,
    loading: adsLoading,
    refetch: refetchAds,
  } = useApi(() => getMyBrandAds(adsParams), [adsParams]);

  const brands: MyBrandRow[] = brandsData?.data ?? [];
  const ads: AdsInsightRow[] = adsData?.data ?? [];
  const adsTotal = adsData?.total ?? 0;

  /* ── Pagination ─────────────────────────────────────────────────────── */
  const currentPageSize = Number(pageSize);
  const currentPage = currentPageSize > 0 ? Math.floor(offset / currentPageSize) + 1 : 1;
  const totalPages = currentPageSize > 0 ? Math.max(1, Math.ceil(adsTotal / currentPageSize)) : 1;

  /* ── Brand search ───────────────────────────────────────────────────── */
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await searchBrands(searchQuery.trim());
      setSearchResults(res.data.data ?? []);
    } catch {
      toast.error("Brand search failed");
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  const handleAddBrand = useCallback(
    async (brand: { external_id: string; name: string; logo_url?: string; active_ads?: number }) => {
      setAddingBrand(brand.name);
      try {
        await addMyBrand({
          brand_name: brand.name,
          brand_external_id: brand.external_id,
          brand_logo_url: brand.logo_url,
          brand_active_ads: brand.active_ads ?? 0,
        });
        toast.success(`"${brand.name}" added to tracking`);
        refetchBrands();
        setSearchResults([]);
        setSearchQuery("");
        // Refetch ads after a short delay to allow scraping to start
        setTimeout(() => refetchAds(), 2000);
      } catch {
        toast.error("Failed to add brand");
      } finally {
        setAddingBrand(null);
      }
    },
    [refetchBrands, refetchAds]
  );

  const handleRemoveBrand = useCallback(
    async (brand: MyBrandRow) => {
      try {
        await removeMyBrand(brand.id);
        toast.success(`"${brand.brand_name}" removed`);
        refetchBrands();
        refetchAds();
      } catch {
        toast.error("Failed to remove brand");
      }
    },
    [refetchBrands, refetchAds]
  );

  const handleRefreshAll = useCallback(async () => {
    try {
      const res = await refreshMyBrandAds();
      toast.success(res.data.message);
    } catch {
      toast.error("Failed to refresh ads");
    }
  }, []);

  const resetFilters = useCallback(() => {
    setBrandFilter("");
    setDateFrom("");
    setDateTo("");
    setPlatformFilter("");
    setOffset(0);
  }, []);

  const hasActiveFilters = brandFilter || dateFrom || dateTo || platformFilter;

  /* ── Collapsible ad groups ─────────────────────────────────────────── */
  const [expandedAdGroups, setExpandedAdGroups] = useState<Set<string>>(new Set());
  const [previewAdId, setPreviewAdId] = useState<string | null>(null);
  const toggleAdGroup = useCallback((key: string) => {
    setExpandedAdGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const groupedAds = useMemo(() => {
    const groups: { key: string; primary: AdsInsightRow; duplicates: AdsInsightRow[] }[] = [];
    const keyMap = new Map<string, number>();
    for (const ad of ads) {
      const title = (ad.title || (ad.body ? String(ad.body).slice(0, 60) : "")).trim().toLowerCase();
      const brand = (ad.brand_name || "").trim().toLowerCase();
      const key = `${brand}|||${title}`;
      const existing = keyMap.get(key);
      if (existing != null) {
        groups[existing].duplicates.push(ad);
      } else {
        keyMap.set(key, groups.length);
        groups.push({ key, primary: ad, duplicates: [] });
      }
    }
    return groups;
  }, [ads]);

  /* ── KPIs ───────────────────────────────────────────────────────────── */
  const adsWithScore = ads.filter((a) => a.performance_score != null && a.performance_score > 0);
  const avgPerfScore =
    adsWithScore.length > 0
      ? (adsWithScore.reduce((s, r) => s + (r.performance_score ?? 0), 0) / adsWithScore.length).toFixed(1)
      : "—";
  const adsWithDays = ads.filter((a) => a.days_active != null && a.days_active > 0);
  const avgDaysActive =
    adsWithDays.length > 0
      ? Math.round(adsWithDays.reduce((s, r) => s + (r.days_active ?? 0), 0) / adsWithDays.length)
      : 0;
  const winningAds = ads.filter(
    (a) => String(a.performance_score_title || "").toLowerCase() === "winning"
  ).length;

  /* ── Chart data ─────────────────────────────────────────────────────── */
  const platformChartData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const ad of ads) {
      for (const p of parsePlatforms(ad.platform)) {
        const key = p.charAt(0).toUpperCase() + p.slice(1).toLowerCase();
        counts[key] = (counts[key] || 0) + 1;
      }
    }
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [ads]);

  const perfChartData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const ad of ads) {
      const tier = ad.performance_score_title || "Unknown";
      counts[tier] = (counts[tier] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [ads]);

  const brandChartData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const ad of ads) {
      const name = ad.brand_name || "Unknown";
      counts[name] = (counts[name] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [ads]);

  /* ── Unique platforms for filter dropdown ────────────────────────────── */
  const allPlatforms = useMemo(() => {
    const set = new Set<string>();
    for (const ad of ads) {
      for (const p of parsePlatforms(ad.platform)) {
        set.add(p.toUpperCase());
      }
    }
    return Array.from(set).sort();
  }, [ads]);

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <div className="p-4 lg:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Megaphone className="w-5 h-5 text-primary" />
            My Ads
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Track and monitor your own brand's ads via GetHooked
          </p>
        </div>
        {brands.length > 0 && (
          <button
            onClick={handleRefreshAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh All Ads
          </button>
        )}
      </div>

      {/* ── Brand Search & Management ─────────────────────────────────── */}
      <div className="bg-card rounded-lg border border-border p-4 space-y-4">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Building2 className="w-4 h-4 text-muted-foreground" />
          Tracked Brands
        </h2>

        {/* Search bar */}
        <div className="flex gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Search for a brand to track..."
              className="w-full h-8 pl-8 pr-3 text-xs border border-input rounded-md bg-transparent focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            Search
          </button>
        </div>

        {/* Search results */}
        {searchResults.length > 0 && (
          <div className="border border-border rounded-md divide-y divide-border">
            {searchResults.map((brand) => (
              <div
                key={brand.external_id}
                className="flex items-center justify-between px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  {brand.logo_url ? (
                    <img
                      src={brand.logo_url}
                      alt={brand.name}
                      className="w-6 h-6 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center">
                      <Building2 className="w-3 h-3 text-muted-foreground" />
                    </div>
                  )}
                  <span className="text-xs font-medium">{brand.name}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {brand.active_ads ?? 0} active ads
                  </span>
                </div>
                <button
                  onClick={() => handleAddBrand(brand)}
                  disabled={addingBrand === brand.name}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium bg-primary/10 text-primary rounded hover:bg-primary/20 transition-colors disabled:opacity-50"
                >
                  {addingBrand === brand.name ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Plus className="w-3 h-3" />
                  )}
                  Track
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Tracked brands list */}
        {brandsLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : brands.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2">
            No brands tracked yet. Search for a brand above to start tracking.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {brands.map((brand) => (
              <div
                key={brand.id}
                className="flex items-center gap-2 px-3 py-1.5 bg-muted/50 rounded-full border border-border"
              >
                {brand.brand_logo_url ? (
                  <img
                    src={brand.brand_logo_url}
                    alt={brand.brand_name}
                    className="w-5 h-5 rounded-full object-cover"
                  />
                ) : (
                  <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center">
                    <Building2 className="w-2.5 h-2.5 text-primary" />
                  </div>
                )}
                <span className="text-xs font-medium">{brand.brand_name}</span>
                <span className="text-[10px] text-muted-foreground">
                  {brand.brand_active_ads ?? 0} ads
                </span>
                <button
                  onClick={() => handleRemoveBrand(brand)}
                  className="ml-1 p-0.5 rounded-full hover:bg-destructive/10 transition-colors"
                  title="Remove brand"
                >
                  <X className="w-3 h-3 text-muted-foreground hover:text-destructive" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── KPI Strip ─────────────────────────────────────────────────── */}
      {brands.length > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: "Total Ads", value: adsTotal, icon: Megaphone, color: "text-primary" },
              { label: "Displayed", value: ads.length, icon: Eye, color: "text-cyan-500" },
              { label: "Avg Performance", value: avgPerfScore, icon: Target, color: "text-amber-500" },
              { label: "Avg Days Active", value: avgDaysActive, icon: Clock, color: "text-emerald-500" },
              { label: "Winning Ads", value: winningAds, icon: TrendingUp, color: "text-violet-500" },
            ].map((kpi) => (
              <div
                key={kpi.label}
                className="bg-card rounded-lg border border-border p-3 flex items-center gap-3"
              >
                <div className={`p-2 rounded-lg bg-muted/50 ${kpi.color}`}>
                  <kpi.icon className="w-4 h-4" />
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                    {kpi.label}
                  </p>
                  <p className="text-lg font-semibold">{kpi.value}</p>
                </div>
              </div>
            ))}
          </div>

          {/* ── Charts ──────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Platform Distribution */}
            <div className="bg-card rounded-lg border border-border p-4">
              <h3 className="text-xs font-semibold mb-3 flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5 text-muted-foreground" />
                Platform Distribution
              </h3>
              {platformChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={platformChartData}
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={70}
                      paddingAngle={2}
                      dataKey="value"
                      label={({ name, percent }) =>
                        `${name} ${(percent * 100).toFixed(0)}%`
                      }
                      labelLine={false}
                    >
                      {platformChartData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-8">No data</p>
              )}
            </div>

            {/* Performance Tiers */}
            <div className="bg-card rounded-lg border border-border p-4">
              <h3 className="text-xs font-semibold mb-3 flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-muted-foreground" />
                Performance Tiers
              </h3>
              {perfChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={perfChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fontSize: 10 }}
                      width={80}
                    />
                    <Tooltip />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                      {perfChartData.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-8">No data</p>
              )}
            </div>

            {/* Ads per Brand */}
            <div className="bg-card rounded-lg border border-border p-4">
              <h3 className="text-xs font-semibold mb-3 flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5 text-muted-foreground" />
                Ads per Brand
              </h3>
              {brandChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={brandChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fontSize: 9 }}
                      width={90}
                    />
                    <Tooltip />
                    <Bar dataKey="value" fill="#6366f1" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-8">No data</p>
              )}
            </div>
          </div>

          {/* ── Filters ─────────────────────────────────────────────────── */}
          <div className="bg-card rounded-lg border border-border p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-muted-foreground" />
                Filters & Pagination
              </h3>
              {hasActiveFilters && (
                <button
                  onClick={resetFilters}
                  className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
                >
                  <X className="w-3 h-3" />
                  Clear filters
                </button>
              )}
            </div>

            <div className="flex flex-wrap gap-3 items-end">
              {/* Page size */}
              <div>
                <label className="text-[10px] text-muted-foreground block mb-1">
                  Per page
                </label>
                <Select
                  value={pageSize}
                  onValueChange={(v) => {
                    setPageSize(v);
                    setOffset(0);
                  }}
                >
                  <SelectTrigger className="h-8 w-20 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAGE_SIZES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Brand filter */}
              {brands.length > 1 && (
                <div>
                  <label className="text-[10px] text-muted-foreground block mb-1">
                    Brand
                  </label>
                  <Select
                    value={brandFilter}
                    onValueChange={(v) => {
                      setBrandFilter(v === "__all__" ? "" : v);
                      setOffset(0);
                    }}
                  >
                    <SelectTrigger className="h-8 w-40 text-xs">
                      <SelectValue placeholder="All brands" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">All brands</SelectItem>
                      {brands.map((b) => (
                        <SelectItem key={b.id} value={b.brand_name}>
                          {b.brand_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Platform filter */}
              {allPlatforms.length > 0 && (
                <div>
                  <label className="text-[10px] text-muted-foreground block mb-1">
                    Platform
                  </label>
                  <Select
                    value={platformFilter}
                    onValueChange={(v) => {
                      setPlatformFilter(v === "__all__" ? "" : v);
                      setOffset(0);
                    }}
                  >
                    <SelectTrigger className="h-8 w-36 text-xs">
                      <SelectValue placeholder="All platforms" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">All platforms</SelectItem>
                      {allPlatforms.map((p) => (
                        <SelectItem key={p} value={p}>
                          {p}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Date range */}
              <div>
                <label className="text-[10px] text-muted-foreground block mb-1">
                  <Calendar className="w-3 h-3 inline mr-0.5" />
                  From
                </label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => {
                    setDateFrom(e.target.value);
                    setOffset(0);
                  }}
                  className="h-8 px-2 text-xs border border-input rounded-md bg-transparent focus:outline-none focus:ring-2 focus:ring-ring/50"
                />
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-1">
                  <Calendar className="w-3 h-3 inline mr-0.5" />
                  To
                </label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => {
                    setDateTo(e.target.value);
                    setOffset(0);
                  }}
                  className="h-8 px-2 text-xs border border-input rounded-md bg-transparent focus:outline-none focus:ring-2 focus:ring-ring/50"
                />
              </div>

              {/* Sort */}
              <div>
                <label className="text-[10px] text-muted-foreground block mb-1">
                  Sort by
                </label>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="h-8 w-32 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="start_date">Start Date</SelectItem>
                    <SelectItem value="days_active">Days Active</SelectItem>
                    <SelectItem value="performance_score">Performance</SelectItem>
                    <SelectItem value="used_count">Used Count</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground block mb-1">
                  Direction
                </label>
                <Select value={sortDir} onValueChange={setSortDir}>
                  <SelectTrigger className="h-8 w-20 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="desc">Desc</SelectItem>
                    <SelectItem value="asc">Asc</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* ── Ads Table ───────────────────────────────────────────────── */}
          <div className="bg-card rounded-lg border border-border overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h3 className="text-xs font-semibold">
                Your Ads ({adsTotal} total)
              </h3>
              {/* Pagination */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => setOffset(Math.max(0, offset - currentPageSize))}
                  disabled={currentPage <= 1}
                  className="p-1 rounded hover:bg-muted disabled:opacity-30"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setOffset(offset + currentPageSize)}
                  disabled={currentPage >= totalPages}
                  className="p-1 rounded hover:bg-muted disabled:opacity-30"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {adsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : ads.length === 0 ? (
              <div className="text-center py-12 text-sm text-muted-foreground">
                No ads found for your tracked brands. Try refreshing or adding more brands.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="text-left px-3 py-2 font-medium">Brand</th>
                      <th className="text-left px-3 py-2 font-medium">Title / Body</th>
                      <th className="text-left px-3 py-2 font-medium">Platform</th>
                      <th className="text-left px-3 py-2 font-medium">Format</th>
                      <th className="text-left px-3 py-2 font-medium">CTA</th>
                      <th className="text-right px-3 py-2 font-medium">Performance</th>
                      <th className="text-right px-3 py-2 font-medium">Days Active</th>
                      <th className="text-left px-3 py-2 font-medium">Start Date</th>
                      <th className="text-center px-3 py-2 font-medium">Link</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {groupedAds.map((group) => {
                      const ad = group.primary;
                      const hasDupes = group.duplicates.length > 0;
                      const isExpanded = expandedAdGroups.has(group.key);
                      const totalInGroup = 1 + group.duplicates.length;

                      const renderRow = (rowAd: AdsInsightRow, idx: number, isChild: boolean) => {
                        const isPreviewOpen = previewAdId === String(rowAd.id);
                        let mediaUrl = rowAd.share_url;
                        let thumbnail = rowAd.brand_logo_url;
                        
                        try {
                          const mediaData = rowAd.media ? JSON.parse(rowAd.media) : [];
                          if (Array.isArray(mediaData) && mediaData.length > 0) {
                            mediaUrl = mediaData[0].url || mediaUrl;
                            thumbnail = mediaData[0].thumbnail_url || thumbnail;
                          }
                        } catch (e) {
                          // ignore
                        }

                        return (
                          <React.Fragment key={rowAd.hookd_id || `${group.key}-${idx}`}>
                            <tr
                              className={`hover:bg-muted/20 ${isChild ? "bg-muted/10" : ""} ${isPreviewOpen ? "bg-primary/5" : ""}`}
                            >
                              <td className="px-3 py-2">
                                <div className="flex items-center gap-1.5">
                                  {!isChild && hasDupes && (
                                    <button
                                      onClick={() => toggleAdGroup(group.key)}
                                      className="shrink-0 p-0.5 rounded hover:bg-muted transition-colors"
                                    >
                                      <ChevronDown
                                        className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${
                                          isExpanded ? "rotate-0" : "-rotate-90"
                                        }`}
                                      />
                                    </button>
                                  )}
                                  {isChild && <span className="w-5 shrink-0" />}
                                  {rowAd.brand_logo_url ? (
                                    <img
                                      src={rowAd.brand_logo_url}
                                      alt=""
                                      className="w-5 h-5 rounded-full object-cover shrink-0"
                                    />
                                  ) : null}
                                  <span className="font-medium truncate max-w-[100px]">
                                    {rowAd.brand_name || "—"}
                                  </span>
                                  {!isChild && hasDupes && (
                                    <span className="shrink-0 text-[9px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                                      {totalInGroup}x
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="px-3 py-2 max-w-[200px]">
                                <div className="flex items-start gap-2">
                                  <button 
                                    onClick={() => setPreviewAdId(isPreviewOpen ? null : String(rowAd.id))}
                                    className={`mt-0.5 p-1 rounded-full transition-colors ${isPreviewOpen ? "bg-primary text-white" : "bg-muted text-muted-foreground hover:bg-primary/20 hover:text-primary"}`}
                                  >
                                    <Play className="w-2.5 h-2.5 fill-current" />
                                  </button>
                                  <div className="min-w-0">
                                    <p className="truncate font-medium">
                                      {rowAd.title || "—"}
                                    </p>
                                    <p className="truncate text-muted-foreground">
                                      {rowAd.body?.slice(0, 60) || ""}
                                    </p>
                                  </div>
                                </div>
                              </td>
                              <td className="px-3 py-2">
                                <div className="flex flex-wrap gap-0.5">
                                  {parsePlatforms(rowAd.platform).map((p) => (
                                    <span
                                      key={p}
                                      className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-[10px]"
                                    >
                                      {p}
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td className="px-3 py-2 text-muted-foreground">
                                {rowAd.display_format || "—"}
                              </td>
                              <td className="px-3 py-2 text-muted-foreground">
                                {rowAd.cta_type || "—"}
                              </td>
                              <td className="px-3 py-2 text-right">
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                    String(rowAd.performance_score_title || "")
                                      .toLowerCase() === "winning"
                                      ? "bg-emerald-500/10 text-emerald-600"
                                      : String(rowAd.performance_score_title || "")
                                          .toLowerCase() === "scaling"
                                      ? "bg-blue-500/10 text-blue-600"
                                      : "bg-muted text-muted-foreground"
                                  }`}
                                >
                                  {rowAd.performance_score_title || "—"}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums">
                                {rowAd.days_active ?? "—"}
                              </td>
                              <td className="px-3 py-2 text-muted-foreground">
                                {rowAd.start_date || "—"}
                              </td>
                              <td className="px-3 py-2 text-center">
                                {rowAd.share_url ? (
                                  <a
                                    href={rowAd.share_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-primary hover:text-primary/80"
                                  >
                                    <ExternalLink className="w-3.5 h-3.5 inline" />
                                  </a>
                                ) : (
                                  "—"
                                )}
                              </td>
                            </tr>
                            {isPreviewOpen && (
                              <tr className="bg-muted/5 border-b border-border">
                                <td colSpan={9} className="px-4 py-4">
                                  <div className="flex flex-col md:flex-row gap-6 max-w-4xl">
                                    <div className="w-full md:w-[300px] shrink-0">
                                      <MediaPreview 
                                        url={mediaUrl} 
                                        thumbnail={thumbnail} 
                                        platform={rowAd.platform}
                                      />
                                    </div>
                                    <div className="flex-1 space-y-4">
                                      <div>
                                        <h4 className="text-sm font-semibold mb-1">{rowAd.title || "Ad Preview"}</h4>
                                        <p className="text-xs text-muted-foreground leading-relaxed">
                                          {rowAd.body || "No additional text content available for this ad."}
                                        </p>
                                      </div>
                                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                                        <div className="space-y-1">
                                          <span className="text-[10px] text-muted-foreground uppercase font-bold">CTA</span>
                                          <p className="text-[11px] font-medium">{rowAd.cta_type || "—"}</p>
                                          <p className="text-[10px] text-muted-foreground italic">{rowAd.cta_text}</p>
                                        </div>
                                        <div className="space-y-1">
                                          <span className="text-[10px] text-muted-foreground uppercase font-bold">Audience</span>
                                          <p className="text-[11px] font-medium">
                                            {rowAd.age_audience_min}-{rowAd.age_audience_max} {rowAd.gender_audience}
                                          </p>
                                        </div>
                                        <div className="space-y-1">
                                          <span className="text-[10px] text-muted-foreground uppercase font-bold">Reach</span>
                                          <p className="text-[11px] font-medium">{formatNumber(rowAd.eu_total_reach)}</p>
                                        </div>
                                        <div className="space-y-1">
                                          <span className="text-[10px] text-muted-foreground uppercase font-bold">Spend Range</span>
                                          <p className="text-[11px] font-medium">{rowAd.ad_spend_range_score_title || "—"}</p>
                                        </div>
                                      </div>
                                      <div className="flex items-center justify-end pt-2">
                                         <a
                                          href={rowAd.share_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-primary hover:underline px-3 py-1.5 bg-primary/5 rounded border border-primary/10"
                                        >
                                          <ExternalLink className="w-3 h-3" /> View In Ad Library
                                        </a>
                                      </div>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      };

                      return (
                        <>
                          {renderRow(ad, 0, false)}
                          {hasDupes && isExpanded &&
                            group.duplicates.map((dup, di) => renderRow(dup, di + 1, true))
                          }
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Bottom pagination */}
            {ads.length > 0 && (
              <div className="flex items-center justify-between px-4 py-2 border-t border-border bg-muted/20">
                <span className="text-[10px] text-muted-foreground">
                  Showing {offset + 1}–{Math.min(offset + ads.length, adsTotal)} of{" "}
                  {adsTotal}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setOffset(Math.max(0, offset - currentPageSize))}
                    disabled={currentPage <= 1}
                    className="p-1 rounded hover:bg-muted disabled:opacity-30"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setOffset(offset + currentPageSize)}
                    disabled={currentPage >= totalPages}
                    className="p-1 rounded hover:bg-muted disabled:opacity-30"
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
