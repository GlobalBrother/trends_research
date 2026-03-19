import sys
import os
import math
import json
import streamlit as st
import pandas as pd
import plotly.express as px

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.dashboard.utils.api_client import APIClient
from src.dashboard.tabs import _apply_modern_layout, GRADIENT_BLUE, GRADIENT_TEAL, GRADIENT_PURPLE, GRADIENT_SUNSET

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Ads Insight — GetHookd AI", layout="wide", page_icon="📢")


def format_number(val):
    if not isinstance(val, (int, float)):
        try:
            val = float(val)
        except Exception:
            return str(val)
    if math.isnan(val) or math.isinf(val):
        return "0"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return str(int(val))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(api):
    with st.sidebar:
        st.subheader("📢 Ads Insight")

        # App switcher for admin users
        if st.session_state.get("user_role") == "admin":
            st.markdown(
                '<div style="font-size:0.75rem;font-weight:600;color:#8b949e;'
                'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem;">'
                '🔀 Switch App</div>',
                unsafe_allow_html=True,
            )
            st.page_link("app.py", label="🚀 Trends Research", use_container_width=True)
            st.page_link("pages/admin.py", label="🛠️ Admin Panel", use_container_width=True)
            st.divider()

        limit = st.slider("Max ads to display", 50, 2000, 500, step=50, key="ads_limit")

    return {"limit": limit}


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def ads_main():
    header_cols = st.columns([8, 1])
    with header_cols[0]:
        st.header("📢 Ads Insight — GetHookd AI")
    with header_cols[1]:
        if st.button("🔄 Refresh", key="ads_refresh"):
            st.cache_data.clear()
            st.rerun()

    api = APIClient()
    cfg = render_sidebar(api)

    df = api.get_ads_insight(limit=cfg["limit"])

    # Ensure numeric columns are properly typed
    for col in ["performance_score", "days_active", "active_in_library", "used_count",
                 "age_audience_min", "age_audience_max", "eu_total_reach",
                 "ad_spend_range_score", "brand_active_ads"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.empty:
        st.info("No ads data found. Use the **Admin** page to fetch ads first.")
        return

    # --- KPI cards ---
    kpi_cols = st.columns(5)
    with kpi_cols[0]:
        st.metric("📊 Total Ads", format_number(len(df)))
    with kpi_cols[1]:
        brands = df["brand_name"].nunique() if "brand_name" in df.columns else 0
        st.metric("🏢 Brands", format_number(brands))
    with kpi_cols[2]:
        avg_score = pd.to_numeric(df["performance_score"], errors="coerce").mean() if "performance_score" in df.columns else 0
        st.metric("⭐ Avg Score", f"{avg_score:.1f}" if pd.notna(avg_score) and avg_score else "—")
    with kpi_cols[3]:
        avg_days = pd.to_numeric(df["days_active"], errors="coerce").mean() if "days_active" in df.columns else 0
        st.metric("📅 Avg Days Active", f"{avg_days:.0f}" if pd.notna(avg_days) and avg_days else "—")
    with kpi_cols[4]:
        platforms = df["platform"].nunique() if "platform" in df.columns else 0
        st.metric("📱 Platforms", format_number(platforms))

    # --- Filters ---
    st.divider()
    filter_cols = st.columns(4)

    with filter_cols[0]:
        keywords = ["All"] + sorted(df["search_keyword"].dropna().unique().tolist()) if "search_keyword" in df.columns else ["All"]
        sel_keyword = st.selectbox("Keyword", keywords, key="ads_filter_kw")

    with filter_cols[1]:
        platforms_list = ["All"] + sorted(df["platform"].dropna().unique().tolist()) if "platform" in df.columns else ["All"]
        sel_platform = st.selectbox("Platform", platforms_list, key="ads_filter_platform")

    with filter_cols[2]:
        formats_list = ["All"] + sorted(df["display_format"].dropna().unique().tolist()) if "display_format" in df.columns else ["All"]
        sel_format = st.selectbox("Format", formats_list, key="ads_filter_format")

    with filter_cols[3]:
        score_range = st.slider(
            "Performance Score",
            min_value=int(df["performance_score"].min()) if "performance_score" in df.columns and df["performance_score"].notna().any() else 0,
            max_value=int(df["performance_score"].max()) if "performance_score" in df.columns and df["performance_score"].notna().any() else 100,
            value=(
                int(df["performance_score"].min()) if "performance_score" in df.columns and df["performance_score"].notna().any() else 0,
                int(df["performance_score"].max()) if "performance_score" in df.columns and df["performance_score"].notna().any() else 100,
            ),
            key="ads_filter_score",
        )

    # Apply filters
    filtered = df.copy()
    if sel_keyword != "All" and "search_keyword" in filtered.columns:
        filtered = filtered[filtered["search_keyword"] == sel_keyword]
    if sel_platform != "All" and "platform" in filtered.columns:
        filtered = filtered[filtered["platform"] == sel_platform]
    if sel_format != "All" and "display_format" in filtered.columns:
        filtered = filtered[filtered["display_format"] == sel_format]
    if "performance_score" in filtered.columns:
        filtered = filtered[
            (filtered["performance_score"] >= score_range[0]) &
            (filtered["performance_score"] <= score_range[1])
        ]

    st.caption(f"Showing **{len(filtered)}** of {len(df)} ads")

    # --- Tabs ---
    tab_table, tab_charts, tab_brands, tab_landing, tab_cta, tab_copy, tab_audience = st.tabs(
        ["📋 Ads Table", "📊 Charts", "🏢 Brands", "🔗 Landing Pages", "🎯 CTAs", "📝 Ad Copy", "👥 Audience"]
    )

    # ---- Table ----
    with tab_table:
        display_cols = [c for c in [
            "brand_name", "title", "body", "platform", "display_format",
            "performance_score", "performance_score_title", "days_active",
            "cta_type", "cta_text", "landing_page", "share_url",
            "start_date", "search_keyword",
        ] if c in filtered.columns]

        search_ads_table = st.text_input("🔍 Search ads…", key="search_ads_table",
                                           placeholder="Type to filter rows…", label_visibility="collapsed")
        show_filtered = filtered[display_cols] if display_cols else filtered
        if search_ads_table:
            mask = show_filtered.apply(
                lambda row: row.astype(str).str.contains(search_ads_table, case=False, na=False).any(), axis=1)
            show_filtered = show_filtered[mask]
        st.dataframe(
            show_filtered,
            hide_index=True, use_container_width=True, height=500,
            column_config={
                "share_url": st.column_config.LinkColumn("Ad Link"),
                "landing_page": st.column_config.LinkColumn("Landing Page"),
                "performance_score": "Score",
                "performance_score_title": "Score Label",
                "days_active": "Days Active",
                "brand_name": "Brand",
                "display_format": "Format",
                "cta_type": "CTA Type",
                "cta_text": "CTA Text",
                "search_keyword": "Keyword",
            },
        )

        # Export
        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", data=csv, file_name="ads_insight.csv", mime="text/csv")

    # ---- Charts ----
    with tab_charts:
        chart_cols = st.columns(2)

        with chart_cols[0]:
            if "platform" in filtered.columns:
                st.markdown("**Ads by Platform**")
                plat_counts = filtered["platform"].value_counts().reset_index()
                plat_counts.columns = ["Platform", "Count"]
                fig = px.pie(plat_counts, names="Platform", values="Count", hole=0.45)
                _apply_modern_layout(fig)
                fig.update_traces(textinfo="percent+label", textfont_size=11,
                                  marker=dict(line=dict(color="#0e1117", width=1.5)))
                st.plotly_chart(fig, use_container_width=True)

        with chart_cols[1]:
            if "display_format" in filtered.columns:
                st.markdown("**Ads by Format**")
                fmt_counts = filtered["display_format"].value_counts().reset_index()
                fmt_counts.columns = ["Format", "Count"]
                fig = px.bar(fmt_counts, x="Format", y="Count", color="Format")
                _apply_modern_layout(fig, showlegend=False, bargap=0.15)
                st.plotly_chart(fig, use_container_width=True)

        chart_cols2 = st.columns(2)

        with chart_cols2[0]:
            if "performance_score" in filtered.columns and filtered["performance_score"].notna().any():
                st.markdown("**Performance Score Distribution**")
                fig = px.histogram(filtered, x="performance_score", nbins=20,
                                   color_discrete_sequence=["#58a6ff"])
                _apply_modern_layout(fig, xaxis_title="Score", yaxis_title="Count")
                st.plotly_chart(fig, use_container_width=True)

        with chart_cols2[1]:
            if "days_active" in filtered.columns and "performance_score" in filtered.columns:
                st.markdown("**Days Active vs Performance Score**")
                fig = px.scatter(filtered, x="days_active", y="performance_score",
                                 color="platform" if "platform" in filtered.columns else None,
                                 hover_name="brand_name" if "brand_name" in filtered.columns else None,
                                 opacity=0.7)
                _apply_modern_layout(fig)
                st.plotly_chart(fig, use_container_width=True)

        if "cta_type" in filtered.columns:
            st.markdown("**CTA Type Distribution**")
            cta_counts = filtered["cta_type"].value_counts().head(15).reset_index()
            cta_counts.columns = ["CTA Type", "Count"]
            fig = px.bar(cta_counts, x="Count", y="CTA Type", orientation="h",
                         color="Count", color_continuous_scale=GRADIENT_TEAL)
            _apply_modern_layout(fig, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    # ---- Brands ----
    with tab_brands:
        if "brand_name" in filtered.columns:
            brand_stats = filtered.groupby("brand_name").agg(
                ad_count=("hookd_id", "count"),
                avg_score=("performance_score", "mean"),
                avg_days=("days_active", "mean"),
                platforms=("platform", "nunique"),
            ).reset_index().sort_values("ad_count", ascending=False)

            brand_stats.columns = ["Brand", "Ads", "Avg Score", "Avg Days Active", "Platforms"]
            brand_stats["Avg Score"] = brand_stats["Avg Score"].round(1)
            brand_stats["Avg Days Active"] = brand_stats["Avg Days Active"].round(0)

            st.metric("🏢 Total Brands", format_number(len(brand_stats)))

            search_brands = st.text_input("🔍 Search brands…", key="search_ads_brands",
                                            placeholder="Type to filter…", label_visibility="collapsed")
            show_brands = brand_stats
            if search_brands:
                mask = brand_stats.apply(
                    lambda row: row.astype(str).str.contains(search_brands, case=False, na=False).any(), axis=1)
                show_brands = brand_stats[mask]
            st.dataframe(
                show_brands,
                hide_index=True, use_container_width=True, height=450,
            )

            # Top brands chart
            top_brands = brand_stats.head(20)
            if len(top_brands) > 1:
                st.markdown("**Top Brands by Ad Count**")
                fig = px.bar(top_brands, x="Ads", y="Brand", orientation="h",
                             color="Avg Score", color_continuous_scale=GRADIENT_BLUE)
                _apply_modern_layout(fig, yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No brand data available.")

    # ---- Landing Pages ----
    with tab_landing:
        if "landing_page" in filtered.columns:
            lp = filtered[filtered["landing_page"].notna() & (filtered["landing_page"] != "")].copy()
            if lp.empty:
                st.info("No landing page data available.")
            else:
                from urllib.parse import urlparse
                lp["domain"] = lp["landing_page"].apply(lambda u: urlparse(str(u)).netloc if pd.notna(u) else "")

                st.metric("🔗 Unique Landing Pages", format_number(lp["landing_page"].nunique()))

                # Top domains
                domain_counts = lp["domain"].value_counts().head(20).reset_index()
                domain_counts.columns = ["Domain", "Ads"]
                dcols = st.columns(2)
                with dcols[0]:
                    st.markdown("**Top Domains**")
                    st.dataframe(domain_counts, hide_index=True, use_container_width=True, height=400)
                with dcols[1]:
                    if len(domain_counts) > 1:
                        fig = px.bar(domain_counts, x="Ads", y="Domain", orientation="h",
                                     color="Ads", color_continuous_scale=GRADIENT_BLUE)
                        _apply_modern_layout(fig, yaxis=dict(autorange="reversed"))
                        st.plotly_chart(fig, use_container_width=True)

                # Landing page table
                st.markdown("**All Landing Pages**")
                lp_display = ["brand_name", "landing_page", "title", "performance_score", "days_active", "platform"]
                lp_display = [c for c in lp_display if c in lp.columns]
                search_lp = st.text_input("🔍 Search landing pages…", key="search_ads_lp",
                                          placeholder="Type to filter…", label_visibility="collapsed")
                lp_show = lp[lp_display].drop_duplicates(subset=["landing_page"]).sort_values(
                    "performance_score", ascending=False, na_position="last"
                ) if "performance_score" in lp.columns else lp[lp_display].drop_duplicates(subset=["landing_page"])
                if search_lp:
                    mask = lp_show.apply(
                        lambda row: row.astype(str).str.contains(search_lp, case=False, na=False).any(), axis=1)
                    lp_show = lp_show[mask]
                st.dataframe(
                    lp_show,
                    hide_index=True, use_container_width=True, height=500,
                    column_config={
                        "landing_page": st.column_config.LinkColumn("Landing Page"),
                        "brand_name": "Brand",
                        "performance_score": "Score",
                        "days_active": "Days Active",
                    },
                )
        else:
            st.info("No landing page data available.")

    # ---- CTAs ----
    with tab_cta:
        has_cta = "cta_type" in filtered.columns or "cta_text" in filtered.columns
        if has_cta:
            cta_df = filtered.copy()
            cta_cols = st.columns(2)

            with cta_cols[0]:
                if "cta_type" in cta_df.columns:
                    st.markdown("**CTA Types**")
                    cta_type_counts = cta_df["cta_type"].value_counts().reset_index()
                    cta_type_counts.columns = ["CTA Type", "Count"]
                    fig = px.pie(cta_type_counts, names="CTA Type", values="Count", hole=0.45)
                    _apply_modern_layout(fig)
                    fig.update_traces(textinfo="percent+label", textfont_size=11,
                                      marker=dict(line=dict(color="#0e1117", width=1.5)))
                    st.plotly_chart(fig, use_container_width=True)

            with cta_cols[1]:
                if "cta_text" in cta_df.columns:
                    st.markdown("**Top CTA Texts**")
                    cta_text_counts = cta_df["cta_text"].value_counts().head(20).reset_index()
                    cta_text_counts.columns = ["CTA Text", "Count"]
                    fig = px.bar(cta_text_counts, x="Count", y="CTA Text", orientation="h",
                                 color="Count", color_continuous_scale=GRADIENT_TEAL)
                    _apply_modern_layout(fig, yaxis=dict(autorange="reversed"))
                    st.plotly_chart(fig, use_container_width=True)

            # CTA performance
            if "cta_type" in cta_df.columns and "performance_score" in cta_df.columns:
                st.markdown("**Avg Performance by CTA Type**")
                cta_perf = cta_df.groupby("cta_type")["performance_score"].agg(["mean", "count"]).reset_index()
                cta_perf.columns = ["CTA Type", "Avg Score", "Ad Count"]
                cta_perf["Avg Score"] = cta_perf["Avg Score"].round(1)
                cta_perf = cta_perf.sort_values("Avg Score", ascending=False)
                st.dataframe(cta_perf, hide_index=True, use_container_width=True)

            # CTA by brand
            if "cta_type" in cta_df.columns and "brand_name" in cta_df.columns:
                st.markdown("**CTA Types by Brand**")
                cta_brand = cta_df.groupby(["brand_name", "cta_type"]).size().reset_index(name="Count")
                cta_brand = cta_brand.sort_values("Count", ascending=False)
                st.dataframe(cta_brand, hide_index=True, use_container_width=True, height=400)
        else:
            st.info("No CTA data available.")

    # ---- Ad Copy ----
    with tab_copy:
        copy_df = filtered.copy()
        has_body = "body" in copy_df.columns and copy_df["body"].notna().any()
        has_title = "title" in copy_df.columns and copy_df["title"].notna().any()

        if has_body or has_title:
            if has_body:
                copy_df["body_length"] = copy_df["body"].fillna("").str.len()
                copy_df["word_count"] = copy_df["body"].fillna("").str.split().str.len()

                mcols = st.columns(3)
                with mcols[0]:
                    st.metric("📝 Avg Body Length", f"{copy_df['body_length'].mean():.0f} chars")
                with mcols[1]:
                    st.metric("📖 Avg Word Count", f"{copy_df['word_count'].mean():.0f} words")
                with mcols[2]:
                    with_title = copy_df["title"].notna().sum() if has_title else 0
                    st.metric("🏷️ Ads with Title", format_number(with_title))

                # Body length vs performance
                if "performance_score" in copy_df.columns:
                    st.markdown("**Body Length vs Performance Score**")
                    fig = px.scatter(copy_df[copy_df["body_length"] > 0], x="body_length", y="performance_score",
                                     color="brand_name" if "brand_name" in copy_df.columns else None,
                                     opacity=0.6, labels={"body_length": "Body Length (chars)", "performance_score": "Score"})
                    _apply_modern_layout(fig)
                    st.plotly_chart(fig, use_container_width=True)

            # Top performing ad copies
            if "performance_score" in copy_df.columns:
                st.markdown("**Top Performing Ad Copies**")
                top_copy_cols = [c for c in ["brand_name", "title", "body", "performance_score", "days_active", "cta_text", "share_url"] if c in copy_df.columns]
                top_copies = copy_df.nlargest(25, "performance_score")[top_copy_cols]
                st.dataframe(
                    top_copies, hide_index=True, use_container_width=True, height=500,
                    column_config={
                        "share_url": st.column_config.LinkColumn("Ad Link"),
                        "brand_name": "Brand",
                        "performance_score": "Score",
                        "body": st.column_config.TextColumn("Body", width="large"),
                    },
                )
        else:
            st.info("No ad copy data available.")

    # ---- Audience ----
    with tab_audience:
        aud_df = filtered.copy()
        has_gender = "gender_audience" in aud_df.columns and aud_df["gender_audience"].notna().any()
        has_age = ("age_audience_min" in aud_df.columns and aud_df["age_audience_min"].notna().any()) or \
                  ("age_audience_max" in aud_df.columns and aud_df["age_audience_max"].notna().any())
        has_spend = "ad_spend_range_score" in aud_df.columns and aud_df["ad_spend_range_score"].notna().any()

        if has_gender or has_age or has_spend:
            acols = st.columns(2)

            with acols[0]:
                if has_gender:
                    st.markdown("**Gender Audience Distribution**")
                    gender_counts = aud_df["gender_audience"].value_counts().reset_index()
                    gender_counts.columns = ["Gender", "Count"]
                    fig = px.pie(gender_counts, names="Gender", values="Count", hole=0.45)
                    _apply_modern_layout(fig)
                    fig.update_traces(textinfo="percent+label", textfont_size=11,
                                      marker=dict(line=dict(color="#0e1117", width=1.5)))
                    st.plotly_chart(fig, use_container_width=True)

            with acols[1]:
                if has_age:
                    st.markdown("**Age Range Distribution**")
                    age_data = aud_df[["age_audience_min", "age_audience_max"]].dropna()
                    if not age_data.empty:
                        age_data["range"] = age_data["age_audience_min"].astype(int).astype(str) + "-" + age_data["age_audience_max"].astype(int).astype(str)
                        age_counts = age_data["range"].value_counts().reset_index()
                        age_counts.columns = ["Age Range", "Count"]
                        fig = px.bar(age_counts, x="Age Range", y="Count", color="Count",
                                     color_continuous_scale=GRADIENT_PURPLE)
                        _apply_modern_layout(fig, bargap=0.15)
                        st.plotly_chart(fig, use_container_width=True)

            if has_spend:
                st.markdown("**Ad Spend Range Distribution**")
                spend_col = "ad_spend_range_score_title" if "ad_spend_range_score_title" in aud_df.columns and aud_df["ad_spend_range_score_title"].notna().any() else "ad_spend_range_score"
                spend_counts = aud_df[spend_col].value_counts().reset_index()
                spend_counts.columns = ["Spend Range", "Count"]
                fig = px.bar(spend_counts, x="Spend Range", y="Count", color="Count",
                             color_continuous_scale=GRADIENT_SUNSET)
                _apply_modern_layout(fig, bargap=0.15)
                st.plotly_chart(fig, use_container_width=True)

            # Audience summary table
            st.markdown("**Audience Targeting by Brand**")
            aud_cols = [c for c in ["brand_name", "gender_audience", "age_audience_min", "age_audience_max",
                                    "ad_spend_range_score_title", "eu_total_reach"] if c in aud_df.columns]
            if aud_cols:
                aud_summary = aud_df[aud_cols].drop_duplicates().sort_values(aud_cols[0])
                st.dataframe(aud_summary, hide_index=True, use_container_width=True, height=400)
        else:
            st.info("No audience data available.")


ads_main()
