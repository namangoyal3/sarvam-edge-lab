import { useState } from "react";
import { post, useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Btn, Banner } from "../ui";

export default function OfflineMode() {
  const { data: q, reload } = useApi("/telemetry/queue");
  const { data: health } = useApi("/health");
  const { data: devices } = useApi("/devices");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const offline = q && !q.network_online;
  const pending = (q?.items ?? []).filter((i: any) => i.state === "pending" || i.state === "failed");

  async function sync(failOnce: boolean) {
    setBusy(true);
    try {
      const r = await post(`/telemetry/sync?fail_once=${failOnce}`);
      setMsg(`synced=${r.synced}, duplicates_skipped=${r.duplicates_skipped}, retrying_with_backoff=${r.retrying_with_backoff}, remaining=${r.remaining_pending}`);
      reload();
    } catch (e: any) {
      setMsg("ERROR: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  const neverConnected = (devices ?? []).filter((d) => d.never_connected);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Offline Mode</h1>

      {offline ? (
        <Banner tone="warn">
          Network is <b>offline</b> — local inference continues; cloud-only requests are queued or
          rejected per policy. Analytics on other pages show <b>local-only / not centrally synced</b>.
          {" "}Telemetry is accumulating in the bounded local queue below.
          {health?.policy_stale && " Policy freshness EXPIRED — high-risk management actions are locked."}
        </Banner>
      ) : (
        <Banner tone="info">Network online. Use the toggle in the top bar to simulate disconnection.</Banner>
      )}
      {msg && <Banner tone="info">{msg}</Banner>}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title={`Offline queue (${pending.length} pending / ${(q?.items ?? []).length} total)`}
          right={
            <>
              <Btn small kind="ghost" disabled={busy} onClick={() => sync(true)}>sync (flaky)</Btn>{" "}
              <Btn small disabled={busy} onClick={() => sync(false)}>sync</Btn>
            </>
          }>
          {pending.length === 0 && !offline && (
            <div className="text-xs text-slate-500">Queue empty — everything is synced.</div>
          )}
          {offline && pending.length > 0 && (
            <div className="text-xs text-amber-300">
              {pending.length} item(s) waiting. “sync (flaky)” simulates one transient failure so you
              can watch exponential backoff before a successful retry.
            </div>
          )}
          {!offline && pending.length > 0 && (
            <div className="text-xs text-slate-400">
              Network restored but items still queued — press sync.
            </div>
          )}
          {pending.length === 0 && offline && (
            <div className="text-xs text-slate-500">
              Nothing queued yet. Disconnect the network and run a cloud-path request, or generate
              telemetry while offline.
            </div>
          )}
        </Card>

        <Card title="Never-connected device">
          {neverConnected.length ? (
            neverConnected.map((d: any) => (
              <div key={d.id} className="space-y-2">
                <div className="text-xs">
                  <span className="font-mono">{d.id}</span> — {d.name}: has never reached a central
                  endpoint. Real-time central analytics are unavailable for it.
                </div>
                <a href={`/api/devices/${d.id}/diagnostics`} target="_blank" rel="noreferrer">
                  <Btn small kind="ghost">download local diagnostic export</Btn>
                </a>
              </div>
            ))
          ) : (
            <div className="text-xs text-slate-500">No never-connected devices in this tenant view.</div>
          )}
        </Card>
      </div>

      <Card title="Queue contents (idempotency keys shown)">
        <Table head={["key", "type", "state", "attempts", "next attempt", "last error", "created"]}>
          {(q?.items ?? []).slice(0, 50).map((i: any) => (
            <Row key={i.id}>
              <Cell mono>{String(i.idempotency_key).slice(0, 20)}</Cell>
              <Cell>{i.payload_type}</Cell>
              <Cell><Pill color={statusColor(i.state)}>{i.state}</Pill></Cell>
              <Cell mono>{i.attempts}</Cell>
              <Cell mono>{i.next_attempt_at?.slice(11, 19) ?? "—"}</Cell>
              <Cell>{i.last_error?.slice(0, 30) ?? "—"}</Cell>
              <Cell mono>{(i.created_at ?? "").slice(11, 19)}</Cell>
            </Row>
          ))}
        </Table>
        <div className="text-[10px] text-slate-500 mt-2">
          Queue is bounded (oldest dropped at 500). Sync is idempotent by event id — replaying cannot
          create duplicates. Failed syncs back off exponentially (2s · 2^attempts, capped 60s).
          Queued inference jobs execute automatically on reconnect.
        </div>
      </Card>
    </div>
  );
}
