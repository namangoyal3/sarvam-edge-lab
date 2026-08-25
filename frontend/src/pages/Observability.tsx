import { useState } from "react";
import { post, useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Btn, Banner, BarChart, fmtMs } from "../ui";

export default function Observability() {
  const [pathFilter, setPathFilter] = useState("");
  const { data: t, reload } = useApi(`/telemetry?limit=200${pathFilter ? `&execution_path=${pathFilter}` : ""}`);
  const { data: summary } = useApi("/analytics/summary");
  const [busy, setBusy] = useState(false);

  async function toggleContent() {
    await post("/system/content-logging", { enabled: !t.content_logging });
    reload();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Observability</h1>
        <div className="flex items-center gap-2">
          <select className="bg-ink-950 border border-ink-700 rounded-lg px-2 py-1.5 text-xs"
            value={pathFilter} onChange={(e) => setPathFilter(e.target.value)}>
            <option value="">all paths</option>
            <option value="local">local</option>
            <option value="cloud_simulator">cloud simulator</option>
            <option value="queued_offline">queued offline</option>
            <option value="policy_blocked">policy blocked</option>
          </select>
          <Btn small kind="ghost" onClick={reload}>refresh</Btn>
        </div>
      </div>

      <Banner tone={t?.content_logging ? "error" : "info"}>
        {t?.warning}{" "}
        <button onClick={toggleContent} className="underline ml-2">
          turn content logging {t?.content_logging ? "OFF" : "ON (demo only)"}
        </button>
      </Banner>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Latency percentiles (successful requests)">
          <div className="flex gap-6">
            {[["p50", summary?.cards.p50_latency_ms], ["p95", summary?.cards.p95_latency_ms]].map(([k, v]: any) => (
              <div key={k}>
                <div className="text-[11px] uppercase text-slate-400">{k}</div>
                <div className="font-mono text-xl">{fmtMs(v)}</div>
              </div>
            ))}
            <div>
              <div className="text-[11px] uppercase text-slate-400">routing split</div>
              <div className="font-mono text-xs mt-1 space-x-3">
                {Object.entries(summary?.routing_split ?? {}).map(([k, v]: any) => (
                  <span key={k}>{k}: <span className="text-slate-100">{v}</span></span>
                ))}
              </div>
            </div>
          </div>
        </Card>
        <Card title="Error taxonomy">
          <BarChart color="#fb7185" data={Object.entries(summary?.error_taxonomy ?? {}).map(([label, value]) => ({ label, value: Number(value) }))} />
        </Card>
        <Card title="Model / runtime distribution">
          <div className="grid grid-cols-2 gap-4">
            <BarChart data={Object.entries(summary?.model_runtime_distribution?.models ?? {}).map(([l, v]) => ({ label: l, value: Number(v) }))} />
            <BarChart color="#38bdf8" data={Object.entries(summary?.model_runtime_distribution?.runtimes ?? {}).map(([l, v]) => ({ label: l, value: Number(v) }))} />
          </div>
        </Card>
        <Card title="Policy decisions (execution path)">
          <BarChart color="#a78bfa" data={Object.entries(summary?.policy_decisions ?? {}).map(([l, v]) => ({ label: l, value: Number(v) }))} />
        </Card>
      </div>

      <Card title={`Device health (${(summary?.device_health ?? []).length})`}>
        <Table head={["device", "status", "battery", "thermal", "compatibility"]}>
          {(summary?.device_health ?? []).map((d: any) => (
            <Row key={d.id}>
              <Cell mono>{d.id}</Cell>
              <Cell><Pill color={statusColor(d.status)}>{d.status}</Pill></Cell>
              <Cell>{d.battery}%</Cell>
              <Cell><Pill color={statusColor(d.thermal)}>{d.thermal}</Pill></Cell>
              <Cell><Pill color={statusColor(d.compat)}>{d.compat}</Pill></Cell>
            </Row>
          ))}
        </Table>
      </Card>

      <Card title={`Event stream (latest ${(t?.events ?? []).length}, privacy-safe fields only)`}>
        <Table head={["event id", "time", "device", "path", "ok", "latency", "conf", "err", "fallback", "bytes in/out", "queue", "synced"]}>
          {(t?.events ?? []).map((e: any) => (
            <Row key={e.event_id}>
              <Cell mono>{e.event_id.slice(0, 16)}</Cell>
              <Cell mono>{e.ts.slice(5, 19)}</Cell>
              <Cell mono>{e.device_id ?? "—"}</Cell>
              <Cell>{e.execution_path}</Cell>
              <Cell>{e.success ? "✓" : "✗"}</Cell>
              <Cell mono>{fmtMs(e.latency_ms)}</Cell>
              <Cell mono>{e.confidence?.toFixed(2) ?? "—"}</Cell>
              <Cell>{e.error_code ?? "—"}</Cell>
              <Cell>{e.fallback_reason ? String(e.fallback_reason).slice(0, 28) : "—"}</Cell>
              <Cell mono>{e.input_bytes}/{e.output_bytes}</Cell>
              <Cell mono>{e.queue_state}</Cell>
              <Cell>{e.synced ? <Pill color="green">synced</Pill> : <Pill color="amber">pending</Pill>}</Cell>
            </Row>
          ))}
        </Table>
        <div className="text-[10px] text-slate-500 mt-2">
          Raw ticket content is never stored unless demo content logging is explicitly enabled above.
          Correlation IDs tie events to audit entries.
        </div>
      </Card>
    </div>
  );
}
