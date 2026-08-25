import { useState } from "react";
import { useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Banner } from "../ui";

export default function AuditLog() {
  const [action, setAction] = useState("");
  const { data } = useApi(`/audit?limit=200${action ? `&action=${action}` : ""}`);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Audit Log</h1>
        <input
          className="bg-ink-950 border border-ink-700 rounded-lg px-2 py-1.5 text-xs font-mono w-64"
          placeholder="filter by action substring (e.g. review)"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        />
      </div>
      <Banner tone="warn">
        This is a <b>demo audit log for interview purposes only</b> — it is append-only within the app
        but is NOT a certified compliance system (no WORM storage, no tamper-evidence, no legal hold).
      </Banner>

      <Card title={`Events (${data?.events?.length ?? 0})`}>
        <Table head={["time", "user", "role", "tenant", "device", "policy ver", "model ver",
          "action", "approval", "correlation id", "reason", "result"]}>
          {(data?.events ?? []).map((e) => (
            <Row key={e.id}>
              <Cell mono>{(e.ts ?? "").slice(0, 19)}</Cell>
              <Cell mono>{e.actor_user ?? "system"}</Cell>
              <Cell>{e.role ?? "—"}</Cell>
              <Cell mono>{e.tenant_id ?? "—"}</Cell>
              <Cell mono>{e.device_id ?? "—"}</Cell>
              <Cell mono>{e.policy_version ?? "—"}</Cell>
              <Cell mono>{e.model_version ?? "—"}</Cell>
              <Cell><Pill color={statusColor(e.action.includes("reject") || e.action.includes("offline") || e.action.includes("rollback") ? "red" : e.action.includes("review") ? "green" : "blue")}>{e.action}</Pill></Cell>
              <Cell>{e.approval_status ?? "—"}</Cell>
              <Cell mono>{e.correlation_id?.slice(0, 14) ?? "—"}</Cell>
              <Cell>{e.reason ? String(e.reason).slice(0, 40) : "—"}</Cell>
              <Cell>{e.result_summary ? String(e.result_summary).slice(0, 42) : "—"}</Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
