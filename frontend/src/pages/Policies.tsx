import { useEffect, useState } from "react";
import { get, post, useApi } from "../api";
import { Card, Pill, Table, Row, Cell, Btn, Banner, Field, inputCls } from "../ui";

const MODES = [
  ["local_only", "Local-only — never cloud"],
  ["local_preferred", "Local-preferred — cloud only if local unavailable"],
  ["cloud_allowed", "Cloud allowed (explicit force permitted)"],
  ["cloud_disabled", "Cloud disabled — same as local_only"],
];

export default function PoliciesPage() {
  const { data: policies, reload } = useApi("/policies");
  const [selId, setSelId] = useState<string>("p-balanced");
  const sel = (policies ?? []).find((p) => p.id === selId);
  const [draft, setDraft] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setDraft(sel ? { ...sel } : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selId, policies?.length]);

  async function save() {
    try {
      const r = await post("/policies", {
        name: draft.name,
        mode: draft.mode,
        offline_queue_enabled: draft.offline_queue_enabled,
        max_input_bytes: Number(draft.max_input_bytes),
        min_confidence: Number(draft.min_confidence),
        hitl_risk_threshold: draft.hitl_risk_threshold,
      });
      setSelId(r.id);
      setMsg(`saved ${r.id} → version v${r.version}`);
      reload();
    } catch (e: any) {
      setMsg("ERROR: " + e.message);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Policy Management</h1>

      <Banner tone="warn">
        Policy is evaluated BEFORE inference. If cloud is prohibited, the system never silently sends
        data to the cloud simulator — it returns a local result, queues the request, routes to human
        review, or returns a clear policy-blocked result.
      </Banner>
      {msg && <Banner tone="info">{msg}</Banner>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title={`Policies (${policies?.length ?? 0})`}>
          <div className="space-y-1">
            {(policies ?? []).map((p) => (
              <button
                key={p.id}
                onClick={() => setSelId(p.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs border ${
                  p.id === selId
                    ? "border-indigo-500/50 bg-indigo-600/10 text-indigo-200"
                    : "border-transparent bg-ink-950 text-slate-300 hover:bg-ink-800"
                }`}
              >
                <div className="font-medium">{p.name}</div>
                <div className="text-[10px] text-slate-500 font-mono">
                  {p.id} · {p.mode} · v{p.version}
                </div>
              </button>
            ))}
            <Btn small kind="ghost" onClick={() => { setDraft({ name: "New policy", mode: "local_preferred", offline_queue_enabled: true, max_input_bytes: 4000, min_confidence: 0.55, hitl_risk_threshold: "high" }); setSelId("__new__"); }}>
              + new policy
            </Btn>
          </div>
        </Card>

        {draft && (
          <Card title={selId === "__new__" ? "Create policy" : `Edit: ${draft.name} (creates next version)`} className="lg:col-span-2">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Name">
                <input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </Field>
              <Field label="Mode">
                <select className={inputCls} value={draft.mode} onChange={(e) => setDraft({ ...draft, mode: e.target.value })}>
                  {MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </Field>
              <Field label="Max input size (bytes)">
                <input type="number" className={inputCls} value={draft.max_input_bytes}
                  onChange={(e) => setDraft({ ...draft, max_input_bytes: e.target.value })} />
              </Field>
              <Field label="Minimum confidence for auto-accept">
                <input type="number" step="0.05" className={inputCls} value={draft.min_confidence}
                  onChange={(e) => setDraft({ ...draft, min_confidence: e.target.value })} />
              </Field>
              <Field label="HITL required at/above risk threshold">
                <select className={inputCls} value={draft.hitl_risk_threshold}
                  onChange={(e) => setDraft({ ...draft, hitl_risk_threshold: e.target.value })}>
                  {["medium", "high", "critical"].map((v) => <option key={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="Offline queue">
                <button
                  onClick={() => setDraft({ ...draft, offline_queue_enabled: !draft.offline_queue_enabled })}
                  className={`${inputCls} text-left`}
                >
                  {draft.offline_queue_enabled ? "allowed" : "disabled"}
                </button>
              </Field>
              <div className="md:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-slate-400 border-t border-ink-700 pt-3">
                <div>allowed data classes<br /><span className="font-mono text-slate-200">support_text</span></div>
                <div>allowed models<br /><span className="font-mono text-slate-200">{(draft.allowed_models ?? []).length ? draft.allowed_models.join(", ") : "all"}</span></div>
                <div>allowed devices<br /><span className="font-mono text-slate-200">{(draft.allowed_device_ids ?? []).length ? draft.allowed_device_ids.join(", ") : "all"}</span></div>
                <div>policy version<br /><span className="font-mono text-slate-200">v{draft.version ?? 1}</span></div>
              </div>
              <div><Btn onClick={save}>Save policy</Btn></div>
            </div>
          </Card>
        )}
      </div>

      <Card title="Decision order enforced by the engine">
        <ol className="list-decimal ml-5 text-xs text-slate-300 space-y-1">
          <li>Input size ≤ max_input_bytes, else <Pill color="red">rejected</Pill></li>
          <li>Data class in allow-list, else rejected</li>
          <li>Model + device in allow-lists, else rejected</li>
          <li>Explicit cloud request + prohibited policy → queue / review / reject (never cloud)</li>
          <li>Local available and preferred → run local</li>
          <li>Cloud prohibited → queue (if enabled &amp; offline) else human review</li>
          <li>Offline → queue or reject per offline_queue setting</li>
          <li>Else cloud simulator fallback</li>
        </ol>
      </Card>
    </div>
  );
}
