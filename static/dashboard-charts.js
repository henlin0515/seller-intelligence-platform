/**
 * Recharts charts for Seller Dashboard (ESM) — visible metrics only.
 */
import React from "react";
import { createRoot } from "react-dom/client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Line,
  LineChart,
} from "recharts";

const COLORS = {
  mtd: "#ee4d2d",
  m1: "#ffb399",
  uv: "#ee4d2d",
  uvM1: "#ff6b4a",
  grid: "#eceef2",
};

function ChartCard({ title, children }) {
  return React.createElement(
    "div",
    { className: "chart-card" },
    React.createElement("h3", null, title),
    React.createElement("div", { className: "chart-root" }, children)
  );
}

function hasSeries(series) {
  const m = series?.mtd;
  const p = series?.m1;
  return (m != null && m !== 0) || (p != null && p !== 0);
}

function MtdM1BarChart({ title, series }) {
  if (!hasSeries(series)) return null;
  const data = [
    { name: "M-1", value: series.m1 ?? 0, fill: COLORS.m1 },
    { name: "MTD", value: series.mtd ?? 0, fill: COLORS.mtd },
  ];
  return React.createElement(
    ChartCard,
    { title },
    React.createElement(
      ResponsiveContainer,
      { width: "100%", height: 210 },
      React.createElement(
        BarChart,
        { data, barGap: 8 },
        React.createElement(CartesianGrid, { strokeDasharray: "3 3", stroke: COLORS.grid, vertical: false }),
        React.createElement(XAxis, { dataKey: "name", tick={{ fontSize: 12, fill: "#6b7280" } }),
        React.createElement(YAxis, { tickFormatter: formatAxis, tick={{ fontSize: 11, fill: "#6b7280" } }),
        React.createElement(Tooltip, {
          formatter: (v) => formatAxis(v),
          contentStyle: { borderRadius: 10, border: "1px solid #e8eaef" },
        }),
        React.createElement(Bar, { dataKey: "value", radius: [8, 8, 0, 0] },
          data.map((entry, i) =>
            React.createElement(Cell, { key: i, fill: entry.fill })
          )
        )
      )
    )
  );
}

function UvTrendChart({ uv }) {
  if (!hasSeries(uv)) return null;
  const data = [
    { period: "M-1", uv: uv.m1 ?? 0 },
    { period: "MTD", uv: uv.mtd ?? 0 },
  ];
  return React.createElement(
    ChartCard,
    { title: "Organic Traffic (UV)" },
    React.createElement(
      ResponsiveContainer,
      { width: "100%", height: 210 },
      React.createElement(
        LineChart,
        { data },
        React.createElement(CartesianGrid, { strokeDasharray: "3 3", stroke: COLORS.grid }),
        React.createElement(XAxis, { dataKey: "period", tick={{ fontSize: 12, fill: "#6b7280" } }),
        React.createElement(YAxis, { tickFormatter: formatAxis, tick={{ fontSize: 11, fill: "#6b7280" } }),
        React.createElement(Tooltip, {
          formatter: (v) => formatAxis(v),
          contentStyle: { borderRadius: 10, border: "1px solid #e8eaef" },
        }),
        React.createElement(Line, {
          type: "monotone",
          dataKey: "uv",
          stroke: COLORS.uv,
          strokeWidth: 3,
          dot: { r: 5, fill: COLORS.uv, strokeWidth: 2, stroke: "#fff" },
          activeDot: { r: 7 },
          name: "UV",
        })
      )
    )
  );
}

function ToolPerformanceChart({ tools }) {
  const data = (tools || []).filter((t) => t.roas_mtd != null || t.adg_mtd != null);
  if (!data.length) return null;
  return React.createElement(
    ChartCard,
    { title: "Channel contribution" },
    React.createElement(
      ResponsiveContainer,
      { width: "100%", height: 210 },
      React.createElement(
        BarChart,
        { data },
        React.createElement(CartesianGrid, { strokeDasharray: "3 3", stroke: COLORS.grid, vertical: false }),
        React.createElement(XAxis, { dataKey: "tool", tick={{ fontSize: 11, fill: "#6b7280" } }),
        React.createElement(YAxis, { tick={{ fontSize: 11, fill: "#6b7280" } }),
        React.createElement(Tooltip, { contentStyle: { borderRadius: 10, border: "1px solid #e8eaef" } }),
        React.createElement(Legend, { wrapperStyle: { fontSize: 12 } }),
        React.createElement(Bar, { dataKey: "roas", fill: COLORS.mtd, name: "ROAS", radius: [6, 6, 0, 0] }),
        React.createElement(Bar, { dataKey: "adg", fill: COLORS.m1, name: "Adg %", radius: [6, 6, 0, 0] })
      )
    )
  );
}

function formatAxis(v) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(Math.round(v * 100) / 100);
}

function DashboardCharts({ charts }) {
  const adgmv = charts.adgmv_ado?.adgmv || {};
  const ado = charts.adgmv_ado?.ado || {};
  const uv = charts.traffic_conversion?.uv || {};

  const children = [
    React.createElement(MtdM1BarChart, { key: "adgmv", title: "ADGMV MTD vs M-1", series: adgmv }),
    React.createElement(MtdM1BarChart, { key: "ado", title: "ADO MTD vs M-1", series: ado }),
    React.createElement(UvTrendChart, { key: "uv", uv }),
    React.createElement(ToolPerformanceChart, { key: "tools", tools: charts.tool_performance }),
  ].filter(Boolean);

  if (!children.length) {
    return React.createElement("p", { className: "dash-loading", style: { gridColumn: "1 / -1" } }, "No chart data for visible metrics.");
  }

  return React.createElement("div", { style: { display: "contents" } }, children);
}

const chartRoots = new Map();

window.renderDashboardCharts = function renderDashboardCharts(charts) {
  const container = document.getElementById("dashboardCharts");
  if (!container) return;

  chartRoots.forEach((root) => root.unmount());
  chartRoots.clear();
  container.innerHTML = "";

  const mount = document.createElement("div");
  mount.style.display = "contents";
  container.appendChild(mount);

  const root = createRoot(mount);
  chartRoots.set(container, root);
  root.render(React.createElement(DashboardCharts, { charts: charts || {} }));
};
