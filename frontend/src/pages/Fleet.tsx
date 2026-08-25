import { useEffect, useState } from "react";
import { get, post, useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Btn, Banner, Field, inputCls } from "../ui";

export default function Fleet() {
  const { data: devices, reload, error } = useApi("/devices");
  const [showEnroll, setShowEnroll] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState<any>({
    name: "", os: "Android 14", ram_gb: 6, cpu: "Octa-core", gpu_npu: "none",
    chipset: "", runtime: "llama-cpp-python",
  });
  const [policies, setPolicies] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [sel, setSel] = useState<{ id: string; action: string } | null>(null);

  useEffect(() => {
    get("/policies").then(setPolicies).catch(() => {});
    get("/models").then(setModels).catch(() => {});
  }, []);

  async function act(id: string, path: string, note: string) {
    try {
      await post(`/devices/${id}/${path}`);
      setMsg(`${id}: ${note}`);
      reload();
    } catch (e: any) {
      setMsg(`ERROR ${id}: ${e.message}`);
    }
  }

  async function enroll() {
    try {
      await post("/devices/enroll", form);
      setShowEnroll(false);
      setMsg("device enrolled");
      reload();
    } catch (e: any) {
      setMsg("ERROR enroll: " + e.message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Device Fleet</h1>
        <Btn onClick={() => setShowEnroll((s) => !s)}>{showEnroll ? "Cancel" : "+ Enroll device"}</Btn>
      </div>
      {error && <Banner tone="error">{error}</Banner>}
      {msg && <Banner tone="info">{msg}</Banner>}

      {showEnroll && (
        <Card title="Enroll a new device">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Name"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="OS"><input className={inputCls} value={form.os} onChange={(e) => setForm({ ...form, os: e.target.value })} /></Field>
            <Field label="RAM (GB)"><input type="number" className={inputCls} value={form.ram_gb} onChange={(e) => setForm({ ...form, ram_gb: Number(e.target.value) })} /></Field>
            <Field label="CPU"><input className={inputCls} value={form.cpu} onChange={(e) => setForm({ ...form, cpu: e.target.value })} /></Field>
            <Field label="GPU / NPU"><input className={inputCls} value={form.gpu_npu} onChange={(e) => setForm({ ...form, gpu_npu: e.target.value })} /></Field>
            <Field label="Chipset"><input className={inputCls} value={form.chipset} onChange={(e) => setForm({ ...form, chipset: e.target.value })} placeholder="e.g. Tensor G3" /></Field>
            <Field label="Runtime">
              <select className={inputCls} value={form.runtime} onChange={(e) => setForm({ ...form, runtime: e.target.value })}>
                {["llama-cpp-python", "onnx-runtime", "coreml", "tflite"].map((r) => <option key={r}>{r}</option>)}
              </select>
            </Field>
            <div className="flex items-end"><Btn onClick={enroll} disabled={!form.name}>Enroll</Btn></div>
          </div>
        </Card>
      )}

      {/* per-action panels */}
      {sel && (
        <Card title={`${sel.action} — ${sel.id}`}>
          {sel.action === "Assign policy" && (
            <PolicyPicker policies={policies} onCancel={() => setSel(null)}
              onPick={async (pid) => {
                await post(`/devices/${sel.id}/policy?policy_id=${pid}`);
                setSel(null); setMsg(`${sel.id}: policy → ${pid}`); reload();
              }} />
          )}
          {sel.action === "Assign model" && (
            <ModelPicker models={models} onCancel={() => setSel(null)}
              onPick={async (mid) => {
                const m = models.find((x) => x.id === mid);
                await act(sel.id, `update?target_model_id=${mid}&target_version=${encodeURIComponent(m.version)}`, `model assigned (${mid})`);
                setSel(null);
              }} />
          )}
          {sel.action === "Trigger update" && (
            <UpdatePanel models={models} onCancel={() => setSel(null)} id={sel.id} done={() => { setSel(null); reload(); }} />
          )}
        </Card>
      )}

      <Card title={`Fleet (${devices?.length ?? 0} devices)`}>
        <Table head={[
          "Device", "Tenant", "OS", "RAM", "Chipset", "NPU/GPU", "Runtime", "Model ver", "Policy",
          "Status", "Batt/Therm", "Last HB", "Compat", "Update", "",
        ]}>
          {(devices ?? []).map((d) => (
            <Row key={d.id}>
              <Cell><span className="font-medium text-slate-100">{d.id}</span><br /><span className="text-[10px] text-slate-500">{d.name}</span></Cell>
              <Cell>{d.tenant_id.replace("t-", "")}</Cell>
              <Cell>{d.os}</Cell>
              <Cell>{d.ram_gb}GB</Cell>
              <Cell>{d.chipset}</Cell>
              <Cell>{d.gpu_npu}</Cell>
              <Cell mono>{d.runtime}</Cell>
              <Cell mono>{d.model_version ?? "—"}</Cell>
              <Cell mono>{d.policy_id}</Cell>
              <Cell><Pill color={statusColor(d.status)}>{d.status}</Pill></Cell>
              <Cell>{d.battery_pct}% · {d.thermal}</Cell>
              <Cell mono>{d.last_heartbeat ? d.last_heartbeat.slice(11, 19) : d.never_connected ? "never" : "—"}</Cell>
              <Cell><Pill color={statusColor(d.compatibility_detail?.status)}>{d.compatibility_detail?.status?.replace("compatible", "compat")}</Pill></Cell>
              <Cell mono>{d.update_status}</Cell>
              <Cell>
                <div className="flex gap-1 flex-wrap max-w-[240px]">
                  {d.status === "online" && (
                    <>
                      <Btn small kind="ghost" onClick={() => act(d.id, "offline", "placed offline")}>offline</Btn>
                    </>
                  )}
                  {d.status !== "online" && (
                    <Btn small kind="success" onClick={() => act(d.id, "reconnect", "reconnected + synced")}>reconnect</Btn>
                  )}
                  <Btn small kind="ghost" onClick={() => setSel({ id: d.id, action: "Trigger update" })}>update…</Btn>
                  <Btn small kind="ghost" onClick={() => act(d.id, "rollback", "model rolled back")}>rollback</Btn>
                  <Btn small kind="ghost" onClick={() => setSel({ id: d.id, action: "Assign policy" })}>policy…</Btn>
                  <Btn small kind="ghost" onClick={() => setSel({ id: d.id, action: "Assign model" })}>model…</Btn>
                  <Btn small kind="danger" onClick={() => act(d.id, "disable", "disabled")}>disable</Btn>
                  <a href={`/api/devices/${d.id}/diagnostics`} target="_blank" rel="noreferrer">
                    <Btn small kind="ghost">diag export</Btn>
                  </a>
                </div>
              </Cell>
            </Row>
          ))}
        </Table>
        <div className="text-[10px] text-slate-500 mt-2">
          Compatibility considers RAM, OS, chipset architecture and runtime against each model's requirements.
        </div>
      </Card>
    </div>
  );
}

function PolicyPicker({ policies, onPick, onCancel }: any) {
  return (
    <div className="flex gap-2 items-end">
      <Field label="Policy">
        <select className={inputCls} defaultValue="" onChange={(e) => e.target.value && onPick(e.target.value)}>
          <option value="">select policy…</option>
          {policies.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.mode}) v{p.version}</option>)}
        </select>
      </Field>
      <Btn small kind="ghost" onClick={onCancel}>cancel</Btn>
    </div>
  );
}

function ModelPicker({ models, onPick, onCancel }: any) {
  return (
    <div className="flex gap-2 items-end">
      <Field label="Model">
        <select className={inputCls} defaultValue="" onChange={(e) => e.target.value && onPick(e.target.value)}>
          <option value="">select model…</option>
          {models.map((m: any) => <option key={m.id} value={m.id}>{m.name} v{m.version}</option>)}
        </select>
      </Field>
      <Btn small kind="ghost" onClick={onCancel}>cancel</Btn>
    </div>
  );
}

function UpdatePanel({ models, id, done, onCancel }: any) {
  const [mid, setMid] = useState(models[0]?.id ?? "");
  const [ver, setVer] = useState("");
  return (
    <div className="flex gap-3 items-end">
      <Field label="Target model">
        <select className={inputCls} value={mid} onChange={(e) => setMid(e.target.value)}>
          {models.map((m: any) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </Field>
      <Field label="Target version">
        <input className={inputCls} value={ver} onChange={(e) => setVer(e.target.value)} placeholder="1.5.0" />
      </Field>
      <Btn onClick={async () => {
        await post(`/devices/${id}/update?target_model_id=${mid}&target_version=${encodeURIComponent(ver || "1.5.0")}`);
        done();
      }}>Deploy update</Btn>
      <Btn kind="ghost" onClick={onCancel || done}>cancel</Btn>
    </div>
  );
}
