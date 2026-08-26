import { useEffect, useState } from "react";
import { get, post, postForm } from "../api";
import {
  Card, Pill, statusColor, KV, Field, inputCls, Btn, Banner, Table, Row, Cell, fmtMs, fmtINR,
} from "../ui";

export default function Playground() {
  const [devices, setDevices] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [text, setText] = useState(
    "My payment of ₹4999 was charged twice this month. Please refund the extra amount urgently."
  );
  const [lang, setLang] = useState("auto");
  const [deviceId, setDeviceId] = useState("DEV-1002");
  const [modelId, setModelId] = useState("");
  const [policyId, setPolicyId] = useState("p-balanced");
  const [forcePath, setForcePath] = useState("");
  const [resp, setResp] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showTrace, setShowTrace] = useState(true);
  const [recent, setRecent] = useState<any[]>([]);
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [voiceOk, setVoiceOk] = useState<boolean | null>(null);

  useEffect(() => {
    get("/devices").then(setDevices).catch(() => {});
    get("/policies").then(setPolicies).catch(() => {});
    get("/inference/voice/status").then((v) => setVoiceOk(v.available)).catch(() => setVoiceOk(false));
    // health decides the default model: a real loaded artifact wins over the fixture
    Promise.all([
      get("/health").catch(() => null),
      get("/models").catch(() => [] as any[]),
    ]).then(([h, m]: [any, any[]]) => {
      if (h) setHealth(h);
      setModels(m);
      const real =
        h?.mode === "real_local" && m.some((x: any) => x.id === h.model_id) ? h.model_id : null;
      setModelId(real ?? m.find((x: any) => x.kind === "fixture")?.id ?? "");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleMic() {
    if (rec) {
      rec.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop());
        setRec(null);
        setBusy(true);
        setErr(null);
        try {
          const form = new FormData();
          form.append("audio", new Blob(chunks, { type: mr.mimeType }), "ticket.webm");
          if (deviceId) form.append("device_id", deviceId);
          if (policyId) form.append("policy_id", policyId);
          if (modelId) form.append("model_id", modelId);
          const r = await postForm("/inference/voice", form);
          if (r.voice?.text) setText(r.voice.text);
          setResp(r);
          setRecent((prev) => [r, ...prev].slice(0, 6));
        } catch (e: any) {
          setErr(String(e.message ?? e));
        } finally {
          setBusy(false);
        }
      };
      mr.start();
      setRec(mr);
    } catch (e: any) {
      setErr("microphone unavailable: " + String(e.message ?? e));
    }
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const r = await post("/inference", {
        text,
        language_hint: lang,
        device_id: deviceId,
        policy_id: policyId,
        model_id: modelId || undefined,
        force_path: forcePath || null,
      });
      setResp(r);
      setRecent((prev) => [r, ...prev].slice(0, 6));
    } catch (e: any) {
      setErr(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Inference Playground</h1>
        {health && (
          <div className="flex items-center gap-2">
            <Pill color={health.mode === "real_local" ? "green" : "amber"}>
              {health.mode === "real_local" ? "real local model" : health.mode}
            </Pill>
            <span className="text-xs text-slate-400 font-mono">
              artifact: {health.model_path} · runtime pref: {health.runtime_preference}
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* input */}
        <Card title="Request">
          <div className="space-y-3">
            <Field label="Support message (English / Hindi / Hinglish)">
              <textarea
                className={inputCls + " h-28 resize-y"}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Language hint">
                <select className={inputCls} value={lang} onChange={(e) => setLang(e.target.value)}>
                  <option value="auto">auto-detect</option>
                  <option value="en">English</option>
                  <option value="hi">Hindi</option>
                  <option value="mixed-hi-en">Mixed Hinglish</option>
                </select>
              </Field>
              <Field label="Device">
                <select className={inputCls} value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
                  {devices.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.id} — {d.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Model">
                <select className={inputCls} value={modelId} onChange={(e) => setModelId(e.target.value)}>
                  {models.map((m: any) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Policy">
                <select className={inputCls} value={policyId} onChange={(e) => setPolicyId(e.target.value)}>
                  {policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.mode})
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Execution path">
                <select className={inputCls} value={forcePath} onChange={(e) => setForcePath(e.target.value)}>
                  <option value="">auto (per policy)</option>
                  <option value="local">force local</option>
                  <option value="cloud">force cloud simulator</option>
                </select>
              </Field>
              <div className="flex items-end gap-2">
                <Btn onClick={run} disabled={busy || !!rec}>
                  {busy ? "Running…" : "Run inference"}
                </Btn>
                {voiceOk && (
                  <Btn kind={rec ? "danger" : "ghost"} onClick={toggleMic} disabled={busy}>
                    {rec ? "◼ Stop & triage" : "🎤 Speak ticket"}
                  </Btn>
                )}
              </div>
            </div>
            {err && <Banner tone="error">{err}</Banner>}
          </div>
        </Card>

        {/* output */}
        <Card
          title="Result"
          right={
            resp && (
              <Pill color={statusColor(resp.status)}>{resp.status}</Pill>
            )
          }
        >
          {!resp && <div className="text-xs text-slate-500 py-8 text-center">Run an inference to see results.</div>}
          {resp && (
            <div className="space-y-3">
              {resp.banner && <Banner tone="warn">{resp.banner}</Banner>}
              {resp.status === "rejected" && (
                <Banner tone="error">Policy-blocked: {resp.fallback_reason}</Banner>
              )}
              {resp.status === "queued_offline" && (
                <Banner tone="info">Queued locally. It will execute automatically on reconnect.</Banner>
              )}
              {resp.voice && (
                <div className="text-xs text-slate-300 border border-ink-700 rounded-lg p-2 bg-ink-950">
                  <span className="text-slate-500">heard ({resp.voice.asr_model}, {resp.voice.asr_latency_ms}ms, on-device): </span>
                  “{resp.voice.text}”
                </div>
              )}
              {resp.result && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <KV k="category" v={<Pill color="indigo">{resp.result.category}</Pill>} mono={false} />
                    <KV k="urgency" v={<Pill color={statusColor(resp.result.urgency)}>{resp.result.urgency}</Pill>} mono={false} />
                    <KV k="language" v={resp.result.language} />
                    <KV k="confidence" v={resp.result.confidence.toFixed(2)} />
                  </div>
                  <div className="text-xs text-slate-300 border border-ink-700 rounded-lg p-2 bg-ink-950">
                    <span className="text-slate-500">next action: </span>
                    {resp.result.suggested_next_action}
                  </div>
                  <div className="text-[11px] text-slate-500 leading-relaxed">{resp.result.explanation}</div>
                </>
              )}
              <div className="grid grid-cols-2 gap-x-4">
                <KV k="latency" v={fmtMs(resp.latency_ms)} />
                <KV k="est. cost" v={fmtINR(resp.estimated_cost_inr)} />
                <KV k="execution path" v={resp.execution_path} />
                <KV k="validation" v={<Pill color={statusColor(resp.validation.status)}>{resp.validation.status}</Pill>} mono={false} />
                <KV k="policy" v={`${resp.policy.id} v${resp.policy.version}`} />
                <KV k="fallback reason" v={resp.fallback_reason ?? "—"} />
                <KV k="model version" v={resp.model.version} />
                <KV k="runtime version" v={resp.model.runtime_version} />
                <KV k="artifact path" v={resp.artifact_path} />
                <KV k="network" v={resp.network_online ? "online" : "offline"} />
                <KV k="audit event" v={resp.audit_event_id} />
                <KV k="correlation id" v={resp.correlation_id} />
              </div>
              {resp.disclaimer && (
                <div className="text-[10px] text-slate-600">{resp.disclaimer}</div>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* technical trace */}
      {resp && (
        <Card
          title="Technical trace"
          right={
            <Btn small kind="ghost" onClick={() => setShowTrace((s) => !s)}>
              {showTrace ? "collapse" : "expand"}
            </Btn>
          }
        >
          {showTrace && (
            <ol className="relative border-l border-ink-700 ml-2 space-y-3">
              {(resp.trace ?? []).map((t: any, i: number) => (
                <li key={i} className="ml-4">
                  <span className="absolute -left-1 w-2 h-2 rounded-full bg-indigo-400 mt-1.5" />
                  <div className="text-xs font-medium text-indigo-300">{t.step}</div>
                  <div className="text-[11px] text-slate-400 font-mono break-all">{t.detail}</div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}

      {recent.length > 0 && (
        <Card title="Recent runs (this session)">
          <Table head={["request", "status", "path", "category", "urgency", "conf", "latency", "cost"]}>
            {recent.map((r) => (
              <Row key={r.request_id}>
                <Cell mono>{r.request_id.slice(0, 14)}…</Cell>
                <Cell><Pill color={statusColor(r.status)}>{r.status}</Pill></Cell>
                <Cell>{r.execution_path}</Cell>
                <Cell>{r.result?.category ?? "—"}</Cell>
                <Cell>{r.result?.urgency ?? "—"}</Cell>
                <Cell>{r.result?.confidence?.toFixed(2) ?? "—"}</Cell>
                <Cell>{fmtMs(r.latency_ms)}</Cell>
                <Cell>{fmtINR(r.estimated_cost_inr)}</Cell>
              </Row>
            ))}
          </Table>
        </Card>
      )}
    </div>
  );
}
