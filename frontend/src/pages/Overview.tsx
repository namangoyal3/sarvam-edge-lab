import { useState } from "react";
import { get, post, useApi } from "../api";
import { Card, Stat, Pill, LineChart, Legend, BarChart, Donut, Table, Row, Cell, Banner, Field, inputCls, Btn, fmtMs } from "../ui";

const C = { local: "#34d399", cloud: "#a78bfa", queued: "#fbbf24", errors: "#fb7185", latency: "#38bdf8" };

export default function Overview() {
  const { data, error, loading } = useApi("/analytics/summary");
  const [costDraft, setCostDraft] = useState<Record<string, number>>({});
  if (loading) return <div className="text-sm text-slate-500">Loading analytics…</div>;
  if (error) return <Banner tone="error">{error}</Banner>;
  const s = data;
  const cards = s.cards;

  async function saveCost() {
    if (Object.keys(costDraft).length === 0) return;
    await post("/analytics/cost-config", costDraft);
    setCostDraft({});
    location.reload();
  }

  const days = (s.series ?? []).map((d: any) => d.day.slice(5));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Overview Dashboard</h1>
        <div className="flex gap-2">
          {s.offline_view && <Pill color="amber">local-only / not centrally synced</Pill>}
          <Pill color={s.data_provenance.includes("generated") ? "violet" : "green"}>
            data: {s.data_provenance}
          </Pill>
        </div>
      </div>

      {/* stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
        <Stat label="Active devices" value={cards.active_devices} />
        <Stat label="Successful workflows" value={cards.successful_workflows.toLocaleString()} />
        <Stat label="Local execution" value={`${cards.local_execution_pct}%`} tone="text-emerald-300" />
        <Stat label="Cloud fallback" value={`${cards.cloud_fallback_pct}%`} tone="text-violet-300" />
        <Stat label="Offline queued events" value={cards.offline_queued_events} tone="text-amber-300" />
        <Stat label="Current model version" value={cards.current_model_version ?? "—"} />
        <Stat label="p50 latency" value={fmtMs(cards.p50_latency_ms)} />
        <Stat label="p95 latency" value={fmtMs(cards.p95_latency_ms)} />
        <Stat
          label="Validation failure rate"
          value={`${cards.validation_failure_rate_pct}%`}
          tone={cards.validation_failure_rate_pct > 2 ? "text-rose-300" : undefined}
        />
        <Stat label="Crash / errors" value={cards.crash_error_count} />
        <Stat label="Pending updates" value={cards.pending_updates} tone={cards.pending_updates ? "text-amber-300" : undefined} />
        <Stat label="Latest eval verdict" value={s.product_metrics.latest_eval_verdict ?? "run eval"} />
      </div>

      {/* charts */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Local vs cloud executions (per day)">
          <LineChart
            labels={days}
            series={[
              { name: "local", color: C.local, points: (s.series ?? []).map((d: any) => d.local) },
              { name: "cloud_simulator", color: C.cloud, points: (s.series ?? []).map((d: any) => d.cloud_simulator) },
              { name: "queued_offline", color: C.queued, points: (s.series ?? []).map((d: any) => d.queued_offline) },
            ]}
          />
          <Legend items={[{ name: "local", color: C.local }, { name: "cloud sim", color: C.cloud }, { name: "queued offline", color: C.queued }]} />
        </Card>
        <Card title="Avg latency over time (successful requests)">
          <LineChart
            labels={days}
            series={[{ name: "avg ms", color: C.latency, points: (s.series ?? []).map((d: any) => d.avg_latency) }]}
          />
          <Legend items={[{ name: "avg latency ms/day", color: C.latency }]} />
        </Card>
        <Card title="Workflow success rate">
          <BarChart
            color="#34d399"
            data={(s.series ?? []).slice(-7).map((d: any) => ({
              label: d.day.slice(5),
              value: Math.round(100 * (d.local + d.cloud_simulator) / Math.max(d.local + d.cloud_simulator + d.errors + d.queued_offline, 1)),
            }))}
          />
          <div className="text-[10px] text-slate-500 mt-1">% successful executions per day (excl. queued)</div>
        </Card>
        <Card title="Fallback reasons">
          <BarChart color="#fbbf24" data={Object.entries(s.fallback_reasons ?? {}).map(([label, value]) => ({ label, value: Number(value) }))} />
        </Card>
        <Card title="Device compatibility">
          <Donut
            centerLabel={String(s.product_metrics.device_compatibility_pct) + "%"}
            segments={[
              { label: "compatible", value: (s.device_health ?? []).filter((d: any) => d.compat === "compatible").length, color: "#34d399" },
              { label: "warning", value: (s.device_health ?? []).filter((d: any) => d.compat === "compatible_with_warning").length, color: "#fbbf24" },
              { label: "incompatible", value: (s.device_health ?? []).filter((d: any) => d.compat === "incompatible").length, color: "#fb7185" },
            ]}
          />
        </Card>
        <Card title="Offline queue size (events routed to queue per day)">
          <BarChart
            color="#38bdf8"
            data={(s.series ?? []).map((d: any) => ({ label: d.day.slice(5), value: d.queued_offline }))}
          />
        </Card>
      </div>

      {/* product metrics */}
      <Card title="Product metrics">
        <Table head={["metric", "value"]}>
          {Object.entries(s.product_metrics)
            .filter(([k]) => !k.endsWith("_note") && k !== "latest_eval_verdict")
            .map(([k, v]) => (
              <Row key={k}>
                <Cell>{k.replace(/_/g, " ")}</Cell>
                <Cell mono>{v === null || v === undefined || v === "" ? "—" : String(v)}</Cell>
              </Row>
            ))}
        </Table>
        {(s.product_metrics as any).critical_field_accuracy_note && (
          <div className="text-[10px] text-slate-500 mt-2">
            critical-field accuracy: {(s.product_metrics as any).critical_field_accuracy_note} · latest eval verdict:{" "}
            {String(s.product_metrics.latest_eval_verdict ?? "n/a")}
          </div>
        )}
      </Card>

      {/* unit economics */}
      <Card title="Cost simulation — unit economics">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-1 space-y-2">
            <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-lg p-3">
              <div className="text-[11px] uppercase text-slate-400">Estimated cost per successful workflow</div>
              <div className="text-2xl font-mono font-semibold text-indigo-300">
                ₹{(s.unit_economics.cost_per_successful_workflow_inr ?? 0).toFixed(3)}
              </div>
              <div className="text-[10px] text-slate-500 mt-1">{s.unit_economics.formula}</div>
            </div>
            <Field label="monthly total estimate">
              <div className="font-mono text-sm">₹{Number(s.unit_economics.monthly_total_estimated_inr ?? 0).toLocaleString("en-IN")}</div>
            </Field>
          </div>
          <div className="lg:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-2">
            {Object.entries(s.unit_economics.assumptions ?? {}).map(([k, cfg]: [string, any]) => (
              <Field key={k} label={cfg.label}>
                <input
                  type="number"
                  step="any"
                  className={inputCls}
                  defaultValue={cfg.value}
                  onChange={(e) => setCostDraft((d) => ({ ...d, [k]: Number(e.target.value) }))}
                />
                <span className="text-[10px] text-slate-600">{cfg.unit}</span>
              </Field>
            ))}
            <div className="flex items-end">
              <Btn small onClick={saveCost} disabled={!Object.keys(costDraft).length}>
                Save assumptions
              </Btn>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
