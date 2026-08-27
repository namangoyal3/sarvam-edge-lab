import { useEffect, useState } from "react";
import { Routes, Route, NavLink, useLocation } from "react-router-dom";
import { get, post, globalState, saveState, bumpRefresh } from "./api";
import { Pill } from "./ui";
import Playground from "./pages/Playground";
import Overview from "./pages/Overview";
import Fleet from "./pages/Fleet";
import Registry from "./pages/Registry";
import PoliciesPage from "./pages/Policies";
import Evals from "./pages/Evals";
import Observability from "./pages/Observability";
import OfflineMode from "./pages/OfflineMode";
import Reviews from "./pages/Reviews";
import AuditLog from "./pages/AuditLog";

const NAV = [
  ["Playground", "/"],
  ["Overview", "/overview"],
  ["Device Fleet", "/fleet"],
  ["Model & Runtime Registry", "/registry"],
  ["Policy Management", "/policies"],
  ["Evals", "/evals"],
  ["Observability", "/observability"],
  ["Offline Mode", "/offline"],
  ["HITL Review Queue", "/reviews"],
  ["Audit Log", "/audit"],
] as const;

export default function App() {
  const [health, setHealth] = useState<any>(null);
  const loc = useLocation();

  const loadHealth = () => get("/health").then(setHealth).catch(() => setHealth(null));
  useEffect(() => {
    loadHealth();
    const t = setInterval(loadHealth, 5000);
    return () => clearInterval(t);
  }, [loc.pathname]);

  const online = health?.network_online;
  const mode = health?.mode;

  async function toggleNetwork() {
    await post("/system/network", { online: !online });
    bumpRefresh();
    loadHealth();
  }

  function setRole(e: React.ChangeEvent<HTMLSelectElement>) {
    globalState.role = e.target.value;
    saveState();
    bumpRefresh();
    forceRender();
  }
  function setTenant(e: React.ChangeEvent<HTMLSelectElement>) {
    globalState.tenant = e.target.value;
    saveState();
    bumpRefresh();
    forceRender();
  }
  const [, setTick] = useState(0);
  function forceRender() {
    setTick((t) => t + 1);
  }

  return (
    <div className="min-h-screen flex">
      {/* sidebar */}
      <aside className="w-60 shrink-0 border-r border-ink-700 bg-ink-900 flex flex-col">
        <div className="px-4 py-4 border-b border-ink-700">
          <div className="text-sm font-bold tracking-tight text-slate-100">
            Sarvam <span className="text-indigo-400">Edge Lab</span>
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            on-device AI product demo · v{health?.app_version ?? "?"}
          </div>
        </div>
        <nav className="flex-1 py-2 overflow-y-auto">
          {NAV.map(([label, to]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `block px-4 py-2 text-xs ${
                  isActive
                    ? "bg-indigo-600/15 text-indigo-300 border-r-2 border-indigo-400"
                    : "text-slate-400 hover:text-slate-200 hover:bg-ink-800"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 text-[10px] text-slate-600 border-t border-ink-700 leading-relaxed">
          Interview demo build. Not Sarvam Edge production software. Simulated outputs are not
          real benchmarks.
        </div>
      </aside>

      {/* main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* topbar */}
        <header className="h-14 shrink-0 border-b border-ink-700 bg-ink-900/70 backdrop-blur flex items-center gap-3 px-5 sticky top-0 z-10">
          <button
            onClick={toggleNetwork}
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition ${
              online
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                : "border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
            }`}
            title="Simulated global network switch"
          >
            <span className={`w-2 h-2 rounded-full ${online ? "bg-emerald-400" : "bg-rose-400"}`} />
            Network {online ? "Online" : "Offline"}
          </button>

          {mode && (
            <Pill color={mode === "real_local" ? "green" : mode === "simulation" ? "blue" : "amber"}>
              {mode === "real_local"
                ? "Real local model"
                : mode === "simulation"
                ? "Simulation mode (no model artifact)"
                : "Fixture fallback"}
            </Pill>
          )}
          {health?.policy_stale && <Pill color="red">POLICY STALE — high-risk actions locked</Pill>}

          <div className="flex-1" />

          <select
            value={globalState.tenant}
            onChange={setTenant}
            className="bg-ink-950 border border-ink-700 rounded-lg px-2 py-1.5 text-xs text-slate-200"
          >
            <option value="t-acme">tenant: Acme Bank</option>
            <option value="t-indmart">tenant: IndMart Retail</option>
          </select>
          <select
            value={globalState.role}
            onChange={setRole}
            className="bg-ink-950 border border-ink-700 rounded-lg px-2 py-1.5 text-xs text-slate-200"
          >
            <option value="admin">role: admin</option>
            <option value="reviewer">role: reviewer</option>
            <option value="viewer">role: viewer (read-only)</option>
          </select>
          <span
            className={`w-2.5 h-2.5 rounded-full ${health ? "bg-emerald-400" : "bg-rose-400"}`}
            title={health ? "API healthy" : "API unreachable"}
          />
        </header>

        {/* persistent model banner: WHAT is answering requests right now, on every page */}
        {health && (
          <div
            className={`shrink-0 px-5 py-1.5 text-[11px] font-mono flex items-center gap-2 border-b ${
              mode === "real_local"
                ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-200"
                : "bg-amber-500/10 border-amber-500/25 text-amber-200"
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${mode === "real_local" ? "bg-emerald-400" : "bg-amber-400"}`} />
            {mode === "real_local" ? (
              <>
                <span className="font-semibold tracking-wide">REAL LOCAL MODEL</span>
                <span className="text-emerald-300/90">
                  {(health.model_path ?? "").split("/").pop()}
                  {health.model_size_mb ? ` · ${health.model_size_mb} MB` : ""}
                  {health.model_id ? ` · ${health.model_id}` : ""}
                </span>
                <span className="text-emerald-400/60">llama.cpp · on this machine · no network required</span>
              </>
            ) : (
              <>
                <span className="font-semibold tracking-wide">
                  {mode === "simulation" ? "SIMULATION MODE" : "FIXTURE FALLBACK"}
                </span>
                <span className="opacity-80">{health.mode_reason}</span>
              </>
            )}
          </div>
        )}

        <main className="flex-1 p-5 max-w-[1400px] w-full mx-auto">
          {!health && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200 mb-4">
              Backend API unreachable at /api — start it with{" "}
              <code className="font-mono">cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000</code>
            </div>
          )}
          <Routes>
            <Route path="/" element={<Playground />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/fleet" element={<Fleet />} />
            <Route path="/registry" element={<Registry />} />
            <Route path="/policies" element={<PoliciesPage />} />
            <Route path="/evals" element={<Evals />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/offline" element={<OfflineMode />} />
            <Route path="/reviews" element={<Reviews />} />
            <Route path="/audit" element={<AuditLog />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
