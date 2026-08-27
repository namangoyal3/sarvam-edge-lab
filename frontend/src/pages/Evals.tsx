import { useState } from "react";
import { get, post, useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Btn, Banner } from "../ui";

export default function Evals() {
  const { data: datasets } = useApi("/evals/datasets");
  const { data: runs, reload } = useApi("/evals");
  const [mode, setMode] = useState("fixture");
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setErr(null);
    try {
      const r = await post("/evals/run", { mode });
      setReport(r);
      reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setRunning(false);
    }
  }

  const fixtureRun = (runs ?? []).find((r: any) => r.mode === "fixture");
  const cloudRun = (runs ?? []).find((r: any) => r.mode === "cloud_sim");

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Evals</h1>

      <Card title="Run evaluation">
        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <div className="text-[11px] uppercase text-slate-400 mb-1">Dataset</div>
            <div className="font-mono text-sm">
              {(datasets ?? [])[0]?.name ?? "—"} v{(datasets ?? [])[0]?.version} ·{" "}
              {(datasets ?? [])[0]?.case_count} cases
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              scenarios: {(datasets ?? [])[0]?.scenarios?.join(", ") || "—"}
            </div>
          </div>
          <select className="bg-ink-950 border border-ink-700 rounded-lg px-2 py-1.5 text-xs"
            value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="fixture">against: simulation engine</option>
            <option value="cloud_sim">against: cloud simulator</option>
            <option value="local">against: local runtime</option>
          </select>
          <Btn onClick={run} disabled={running}>{running ? "Running…" : "Run eval"}</Btn>
        </div>
        {err && <Banner tone="error">{err}</Banner>}
      </Card>

      {report && (
        <>
          <Card title={`Eval report ${report.eval_run_id}`} right={<Pill color={statusColor(report.verdict_pass)}>{report.verdict_pass}</Pill>}>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <Metric label="Task accuracy" v={report.metrics.task_accuracy} />
              <Metric label="Exact-match" v={report.metrics.exact_match_accuracy} />
              <Metric label="Schema validity" v={report.metrics.schema_validity_rate} />
              <Metric label="Confidence MAE" v={report.metrics.calibration_mae} invert />
              <Metric label="Failures / fallbacks" v={`${report.metrics.failure_count} / ${report.metrics.fallback_count}`} />
              <Metric label="p50 latency" v={`${report.metrics.p50_latency_ms}ms`} />
              <Metric label="p95 latency" v={`${report.metrics.p95_latency_ms}ms`} />
            </div>

            <h4 className="text-xs font-semibold text-slate-300 mb-2">Critical-field gates (aggregate accuracy alone is not used)</h4>
            <Table head={["gate", "rate", "threshold", "verdict"]}>
              {Object.entries(report.gates).map(([k, g]: any) => (
                <Row key={k}>
                  <Cell>{k.replace("_gate", " gate").replace("names", "names")}</Cell>
                  <Cell mono>{g.rate === null ? "n/a" : `${Math.round(g.rate * 100)}%`}</Cell>
                  <Cell mono>{Math.round(g.threshold * 100)}%</Cell>
                  <Cell>
                    <Pill color={g.pass === null ? "gray" : g.pass ? "green" : "red"}>
                      {g.pass === null ? "not exercised" : g.pass ? "PASS" : "FAIL"}
                    </Pill>
                  </Cell>
                </Row>
              ))}
            </Table>
            {report.label && (
              <div className="mt-2"><Pill color="amber">{report.label}</Pill></div>
            )}
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Breakdown title="Results by language" data={report.breakdowns.by_language} />
            <Breakdown title="Results by scenario" data={report.breakdowns.by_scenario} />
            <Breakdown title="Results by device archetype" data={report.breakdowns.by_device} />
          </div>
        </>
      )}

      {/* compare */}
      {cloudRun && fixtureRun && cloudRun.id !== fixtureRun.id && (
        <Card title="Compare latest runs: local/simulation vs cloud simulator">
          <Table head={["metric", "simulation / local", "cloud simulator", "Δ"]}>
            {["task_accuracy", "exact_match_accuracy", "schema_validity_rate", "p95_latency_ms"].map((m) => {
              const a = fixtureRun.metrics[m];
              const b = cloudRun.metrics[m];
              return (
                <Row key={m}>
                  <Cell>{m.replace(/_/g, " ")}</Cell>
                  <Cell mono>{a}</Cell>
                  <Cell mono>{b}</Cell>
                  <Cell mono>{typeof a === "number" && typeof b === "number" ? (b - a >= 0 ? "+" : "") + (b - a).toFixed(3) : "—"}</Cell>
                </Row>
              );
            })}
          </Table>
          <div className="text-[10px] text-slate-500 mt-2">
            Cloud-simulator numbers are synthetic and NOT real Sarvam cloud benchmarks.
          </div>
        </Card>
      )}

      <Card title="Run history">
        <Table head={["run", "model", "mode", "accuracy", "schema valid", "p95", "started"]}>
          {(runs ?? []).map((r: any) => (
            <Row key={r.id}>
              <Cell mono>{r.id}</Cell>
              <Cell mono>
                <span className={String(r.model_id).includes("v3") ? "text-emerald-300" : ""}>
                  {r.model_id ?? "—"}
                </span>
              </Cell>
              <Cell><Pill color={r.mode === "cloud_sim" ? "violet" : "blue"}>{r.mode}</Pill></Cell>
              <Cell mono>{r.metrics.task_accuracy}</Cell>
              <Cell mono>{r.metrics.schema_validity_rate}</Cell>
              <Cell mono>{r.metrics.p95_latency_ms}ms</Cell>
              <Cell mono>{(r.started_at ?? "").slice(0, 19)}</Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}

function Metric({ label, v, invert }: any) {
  return (
    <div className="bg-ink-950 border border-ink-700 rounded-lg p-2.5">
      <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`font-mono text-lg ${invert && Number(v) > 0.15 ? "text-rose-300" : "text-slate-100"}`}>{String(v)}</div>
    </div>
  );
}

function Breakdown({ title, data }: any) {
  return (
    <Card title={title}>
      <Table head={["bucket", "n", "accuracy", "schema valid"]}>
        {Object.entries(data ?? {}).map(([k, v]: any) => (
          <Row key={k}>
            <Cell>{k}</Cell>
            <Cell mono>{v.n}</Cell>
            <Cell mono>{v.accuracy}</Cell>
            <Cell mono>{v.schema_validity}</Cell>
          </Row>
        ))}
      </Table>
    </Card>
  );
}
