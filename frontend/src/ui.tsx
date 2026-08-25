import React from "react";

export function Card({
  title,
  right,
  children,
  className = "",
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-ink-900 border border-ink-700 rounded-xl p-4 ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-3">
          {title && <h3 className="text-sm font-semibold text-slate-300">{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

const pillColors: Record<string, string> = {
  green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  red: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  blue: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  indigo: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  gray: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  violet: "bg-violet-500/15 text-violet-300 border-violet-500/30",
};

export function Pill({
  color = "gray",
  children,
  className = "",
}: {
  color?: keyof typeof pillColors;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md border text-xs font-medium ${pillColors[color]} ${className}`}
    >
      {children}
    </span>
  );
}

export function statusColor(s: string): keyof typeof pillColors {
  if (["online", "completed", "compatible", "valid", "success", "PASS", "synced", "approved"].includes(s))
    return "green";
  if (["offline", "rejected", "incompatible", "invalid", "failed", "FAIL", "critical", "high"].includes(s))
    return "red";
  if (["compatible_with_warning", "needs_review", "queued_offline", "pending", "pending_sync", "elevated", "medium", "open"].includes(s))
    return "amber";
  if (["local", "up_to_date", "resolved", "low"].includes(s)) return "blue";
  if (["cloud_simulator", "rolled_back", "disabled"].includes(s)) return "violet";
  return "gray";
}

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="bg-ink-900 border border-ink-700 rounded-xl p-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`text-xl font-semibold mt-1 font-mono ${tone ?? "text-slate-100"}`}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export function KV({ k, v, mono = true }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-2 py-1 border-b border-ink-800 last:border-0">
      <span className="text-xs text-slate-400">{k}</span>
      <span className={`text-xs text-slate-200 text-right ${mono ? "font-mono" : ""}`}>{v}</span>
    </div>
  );
}

export function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-ink-700">
            {head.map((h) => (
              <th key={h} className="text-[11px] uppercase tracking-wide text-slate-400 py-2 pr-4 whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ children }: { children: React.ReactNode }) {
  return <tr className="border-b border-ink-800 hover:bg-ink-800/40">{children}</tr>;
}

export function Cell({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td className={`py-1.5 pr-4 text-xs whitespace-nowrap ${mono ? "font-mono" : ""} text-slate-200`}>
      {children}
    </td>
  );
}

// ---------- hand-rolled SVG charts (no chart lib needed) ----------

export function LineChart({
  series,
  height = 140,
  labels,
}: {
  series: { name: string; color: string; points: number[] }[];
  height?: number;
  labels?: string[];
}) {
  const w = 560;
  const pad = 24;
  const all = series.flatMap((s) => s.points);
  const max = Math.max(1, ...all);
  const n = Math.max(1, series[0]?.points.length ?? 1);
  const x = (i: number) => pad + (i * (w - 2 * pad)) / Math.max(n - 1, 1);
  const y = (v: number) => height - pad - (v / max) * (height - 2 * pad);
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="w-full">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={pad} x2={w - pad} y1={y(max * f)} y2={y(max * f)} stroke="#1e293b" strokeWidth="1" />
      ))}
      {series.map((s) => (
        <g key={s.name}>
          <polyline
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            points={s.points.map((p, i) => `${x(i)},${y(p)}`).join(" ")}
          />
          {s.points.map((p, i) => (
            <circle key={i} cx={x(i)} cy={y(p)} r="2.5" fill={s.color} />
          ))}
        </g>
      ))}
      {labels &&
        labels.map((l, i) =>
          i % Math.ceil(labels.length / 7 || 1) === 0 ? (
            <text key={i} x={x(i)} y={height - 6} fontSize="9" fill="#64748b" textAnchor="middle">
              {l}
            </text>
          ) : null
        )}
    </svg>
  );
}

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="flex gap-3 flex-wrap mt-1">
      {items.map((i) => (
        <span key={i.name} className="inline-flex items-center gap-1 text-[11px] text-slate-400">
          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: i.color }} />
          {i.name}
        </span>
      ))}
    </div>
  );
}

export function BarChart({
  data,
  color = "#818cf8",
  height = 150,
}: {
  data: { label: string; value: number }[];
  color?: string;
  height?: number;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="space-y-1.5" style={{ minHeight: height }}>
      {data.length === 0 && <div className="text-xs text-slate-500">No data</div>}
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-2">
          <div className="w-36 shrink-0 truncate text-[11px] text-slate-400" title={d.label}>
            {d.label}
          </div>
          <div className="flex-1 bg-ink-800 rounded h-4 overflow-hidden">
            <div
              className="h-full rounded"
              style={{ width: `${(d.value / max) * 100}%`, background: color }}
            />
          </div>
          <div className="w-10 text-right text-[11px] font-mono text-slate-300">{d.value}</div>
        </div>
      ))}
    </div>
  );
}

export function Donut({
  segments,
  size = 120,
  centerLabel,
}: {
  segments: { label: string; value: number; color: string }[];
  size?: number;
  centerLabel?: string;
}) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const r = 42;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox="0 0 110 110">
        <circle cx="55" cy="55" r={r} fill="none" stroke="#182238" strokeWidth="14" />
        {segments.map((s) => {
          const len = (s.value / total) * c;
          const el = (
            <circle
              key={s.label}
              cx="55"
              cy="55"
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth="14"
              strokeDasharray={`${len} ${c - len}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 55 55)"
            />
          );
          offset += len;
          return el;
        })}
        <text x="55" y="58" textAnchor="middle" fontSize="13" fill="#e2e8f0" fontFamily="monospace">
          {centerLabel ?? total}
        </text>
      </svg>
      <Legend items={segments.map((s) => ({ name: `${s.label} (${s.value})`, color: s.color }))} />
    </div>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-[11px] uppercase tracking-wide text-slate-400 mb-1">{label}</span>
      {children}
    </label>
  );
}

export const inputCls =
  "w-full bg-ink-950 border border-ink-700 rounded-lg px-2.5 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 font-mono";

export function Btn({
  children,
  onClick,
  kind = "primary",
  disabled,
  small,
  type,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  kind?: "primary" | "ghost" | "danger" | "success";
  disabled?: boolean;
  small?: boolean;
  type?: "button" | "submit";
}) {
  const kinds = {
    primary: "bg-indigo-600 hover:bg-indigo-500 text-white",
    ghost: "bg-ink-800 hover:bg-ink-700 text-slate-200 border border-ink-700",
    danger: "bg-rose-600/90 hover:bg-rose-500 text-white",
    success: "bg-emerald-600 hover:bg-emerald-500 text-white",
  };
  return (
    <button
      type={type ?? "button"}
      disabled={disabled}
      onClick={onClick}
      className={`${kinds[kind]} ${small ? "text-[11px] px-2 py-1" : "text-xs px-3 py-1.5"} rounded-lg font-medium disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}

export function Banner({
  tone,
  children,
}: {
  tone: "warn" | "info" | "error";
  children: React.ReactNode;
}) {
  const tones = {
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-200",
    info: "border-sky-500/40 bg-sky-500/10 text-sky-200",
    error: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  };
  return (
    <div className={`${tones[tone]} border rounded-lg px-3 py-2 text-xs leading-relaxed`}>
      {children}
    </div>
  );
}

export function fmtMs(v?: number | null) {
  if (v === null || v === undefined) return "—";
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${v}ms`;
}

export function fmtINR(v?: number | null) {
  if (v === null || v === undefined) return "—";
  return `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 })}`;
}
