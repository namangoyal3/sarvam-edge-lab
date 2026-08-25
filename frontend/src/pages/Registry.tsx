import { useEffect, useState } from "react";
import { get, post, useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Btn, Banner, Field, inputCls } from "../ui";

export default function Registry() {
  const [deviceId, setDeviceId] = useState("");
  const [devices, setDevices] = useState<any[]>([]);
  const { data: models, reload } = useApi(`/models${deviceId ? `?device_id=${deviceId}` : ""}`);
  const [showReg, setShowReg] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState<any>({
    id: "", name: "", task: "text-generation", param_count: "~2B", artifact_size_mb: 1310,
    precision: "int4", quantization: "Q4_K_M", runtime: "llama.cpp family",
    supported_os: "linux, macos, windows, android", min_ram_gb: 4, recommended_ram_gb: 6,
    expected_latency_ms: 450, version: "1.0.0", kind: "local",
  });

  useEffect(() => {
    get("/devices").then((d) => {
      setDevices(d);
      if (!deviceId && d.length) setDeviceId(d[0].id);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function register() {
    try {
      await post("/models/register", {
        ...form,
        supported_os: form.supported_os.split(",").map((s: string) => s.trim()).filter(Boolean),
        supported_chipsets: [],
        supported_runtimes: ["llama-cpp-python"],
      });
      setShowReg(false);
      setMsg("model registered");
      reload();
    } catch (e: any) {
      setMsg("ERROR: " + e.message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Model &amp; Runtime Registry</h1>
        <Btn onClick={() => setShowReg((s) => !s)}>{showReg ? "Cancel" : "+ Register model"}</Btn>
      </div>
      {msg && <Banner tone="info">{msg}</Banner>}

      <Banner tone="info">
        Sarvam-1 entries are placeholders for a <b>user-provided public artifact</b> (set
        SARVAM_MODEL_PATH). The demo never downloads unofficial conversions and never claims private
        Sarvam Edge ASR/TTS artifacts.
      </Banner>

      {showReg && (
        <Card title="Register model artifact metadata">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[["id", "id"], ["name", "name"], ["version", "version"], ["task", "task"],
              ["param_count", "param count"], ["artifact_size_mb", "size (MB)"],
              ["quantization", "quantisation"], ["min_ram_gb", "min RAM (GB)"],
              ["recommended_ram_gb", "rec RAM (GB)"], ["expected_latency_ms", "expected latency (ms)"],
              ["supported_os", "supported OS (comma-sep)"]].map(([k, label]) => (
              <Field key={k} label={label}>
                <input className={inputCls} value={(form as any)[k]}
                  onChange={(e) => setForm({ ...form, [k]: k.endsWith("_mb") || k.includes("ram") || k.includes("latency") ? Number(e.target.value) : e.target.value })} />
              </Field>
            ))}
            <div className="flex items-end"><Btn onClick={register} disabled={!form.id || !form.name}>Register</Btn></div>
          </div>
        </Card>
      )}

      <Card
        title="Models"
        right={
          <select className="bg-ink-950 border border-ink-700 rounded-lg px-2 py-1 text-xs" value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}>
            {devices.map((d) => <option key={d.id} value={d.id}>compat vs {d.id} ({d.ram_gb}GB)</option>)}
          </select>
        }
      >
        <Table head={["ID / name", "Task", "Params", "Size", "Prec / Quant", "Runtime", "OS support",
          "Min RAM", "Exp. latency", "Version", "Release status", "Checksum", "Signature", "Compatibility"]}>
          {(models ?? []).map((m) => (
            <Row key={m.id}>
              <Cell><span className="text-slate-100">{m.name}</span><br /><span className="font-mono text-[10px] text-slate-500">{m.id}</span></Cell>
              <Cell>{m.task}</Cell>
              <Cell mono>{m.param_count ?? "—"}</Cell>
              <Cell mono>{m.artifact_size_mb ? `${m.artifact_size_mb} MB` : "—"}</Cell>
              <Cell mono>{m.precision} / {m.quantization}</Cell>
              <Cell mono>{m.runtime}</Cell>
              <Cell mono>{(m.supported_os ?? []).join(", ") || "any"}</Cell>
              <Cell mono>{m.min_ram_gb}GB{m.recommended_ram_gb ? ` (rec ${m.recommended_ram_gb})` : ""}</Cell>
              <Cell mono>~{m.expected_latency_ms}ms</Cell>
              <Cell mono>{m.version}</Cell>
              <Cell><Pill color={m.release_status === "demo_fixture" ? "blue" : m.release_status === "external_artifact_required" ? "amber" : "gray"}>{m.release_status}</Pill></Cell>
              <Cell mono>{m.checksum ?? "—"}</Cell>
              <Cell mono>{m.signature}</Cell>
              <Cell>
                {m.compatibility ? (
                  <span title={(m.compatibility.reasons ?? []).join("; ")}>
                    <Pill color={statusColor(m.compatibility.status)}>{m.compatibility.status}</Pill>
                    <div className="text-[10px] text-slate-500 max-w-[220px] truncate mt-0.5">
                      {(m.compatibility.reasons ?? [])[0]}
                    </div>
                  </span>
                ) : "—"}
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>

      <Runtimes />
    </div>
  );
}

function Runtimes() {
  const { data } = useApi("/telemetry?limit=500");
  // runtime registry is seeded; show static info via models' runtimes + telemetry distribution
  return (
    <Card title="Runtime registry (seeded)">
      <Table head={["Runtime", "Version", "Backend", "Supported OS", "Notes"]}>
        {[
          ["llama-cpp-python", "0.2.90", "CPU (AVX2/NEON), Metal, CUDA", "linux, macos, windows", "primary local runtime for GGUF artifacts"],
          ["onnx-runtime", "1.18", "CPU, DirectML, CoreML", "linux, macos, windows", "used on Windows laptops"],
          ["coreml-tools runtime", "4.0", "ANE/GPU", "macos, ios", "Apple devices"],
          ["tensorflow-lite", "2.16", "NNAPI/GPU delegate", "android", "low-end Android"],
          ["cloud-simulator", "1.1", "in-process", "any", "NOT a real cloud API"],
        ].map((r) => (
          <Row key={r[0]}>
            <Cell mono>{r[0]}</Cell><Cell mono>{r[1]}</Cell><Cell>{r[2]}</Cell>
            <Cell mono>{r[3]}</Cell><Cell>{r[4]}</Cell>
          </Row>
        ))}
      </Table>
    </Card>
  );
}
