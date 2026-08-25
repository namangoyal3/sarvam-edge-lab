import { useState } from "react";
import { post, useApi } from "../api";
import { Card, Pill, statusColor, Table, Row, Cell, Btn, Banner, Field, inputCls } from "../ui";

export default function Reviews() {
  const [tab, setTab] = useState("open");
  const { data: reviews, reload } = useApi(`/reviews?status=${tab === "all" ? "" : tab}`);
  const [editing, setEditing] = useState<any>(null);
  const [corrected, setCorrected] = useState<any>({});
  const [reason, setReason] = useState("");

  async function act(id: string, action: string) {
    try {
      await post(`/reviews/${id}/action`, {
        action,
        reason: reason || `${action} via demo UI`,
        corrected: action === "edit" ? corrected : undefined,
      });
      setEditing(null);
      setCorrected({});
      setReason("");
      reload();
    } catch (e: any) {
      alert(e.message);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">HITL Review Queue</h1>
      <Banner tone="info">
        Cases land here on low confidence, high-risk categories (data privacy / security), invalid
        structured outputs, stale offline results and policy exceptions. Every reviewer action writes
        an immutable audit trail entry. Requires <b>reviewer</b> or <b>admin</b> role.
      </Banner>

      <div className="flex gap-2">
        {["open", "resolved", "rejected", "all"].map((t) => (
          <Btn key={t} small kind={tab === t ? "primary" : "ghost"} onClick={() => setTab(t)}>
            {t}
          </Btn>
        ))}
      </div>

      {(reviews ?? []).length === 0 && (
        <Card><div className="text-xs text-slate-500 py-6 text-center">No review tasks with status “{tab}”.</div></Card>
      )}

      {(reviews ?? []).map((r) => (
        <Card key={r.id}>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="space-y-1 min-w-0">
              <div className="flex gap-2 items-center flex-wrap">
                <Pill color={statusColor(r.reason_code)}>{r.reason_code}</Pill>
                <Pill color={statusColor(r.status)}>{r.status}</Pill>
                <span className="font-mono text-[10px] text-slate-500">{r.id} · req {r.request_id}</span>
              </div>
              <div className="text-xs text-slate-300">
                original → category <span className="font-mono text-indigo-300">{r.original_result?.category}</span>, urgency{" "}
                <span className="font-mono text-amber-300">{r.original_result?.urgency}</span>, confidence{" "}
                <span className="font-mono">{r.original_result?.confidence?.toFixed?.(2)}</span>
              </div>
              <div className="text-[11px] text-slate-500 max-w-xl">{r.detail}</div>
              {r.resolved_result && (
                <div className="text-[11px] text-emerald-300/80">
                  resolved result → {r.resolved_result.category} / {r.resolved_result.urgency}
                  {r.resolution_note ? ` — “${r.resolution_note}”` : ""}
                </div>
              )}
            </div>

            {r.status === "open" && (
              <div className="flex flex-col gap-1.5 shrink-0">
                <div className="flex gap-1.5">
                  <Btn small kind="success" onClick={() => act(r.id, "approve")}>approve</Btn>
                  <Btn small kind="danger" onClick={() => act(r.id, "reject")}>reject</Btn>
                  <Btn small kind="ghost" onClick={() => { setEditing(editing === r.id ? null : r.id); setCorrected({
                    category: r.original_result?.category,
                    urgency: r.original_result?.urgency,
                    suggested_next_action: r.original_result?.suggested_next_action ?? "",
                  }); }}>edit…</Btn>
                </div>
                <input className={inputCls + " w-56"} placeholder="reason (audit trail)"
                  value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>
            )}
          </div>

          {editing === r.id && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 border-t border-ink-700 pt-3">
              <Field label="corrected category">
                <select className={inputCls} value={corrected.category}
                  onChange={(e) => setCorrected({ ...corrected, category: e.target.value })}>
                  {["billing", "connectivity", "account_access", "performance", "data_privacy", "security", "feature_request", "other"].map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="corrected urgency">
                <select className={inputCls} value={corrected.urgency}
                  onChange={(e) => setCorrected({ ...corrected, urgency: e.target.value })}>
                  {["low", "medium", "high", "critical"].map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="corrected next action">
                <input className={inputCls} value={corrected.suggested_next_action ?? ""}
                  onChange={(e) => setCorrected({ ...corrected, suggested_next_action: e.target.value })} />
              </Field>
              <div><Btn onClick={() => act(r.id, "edit")}>save edit (v+1)</Btn></div>
            </div>
          )}

          {/* immutable audit trail */}
          <details className="mt-3">
            <summary className="text-[11px] text-slate-400 cursor-pointer">audit trail ({(r.audit_trail ?? []).length})</summary>
            <Table head={["time", "action", "actor", "role", "approval", "reason"]}>
              {(r.audit_trail ?? []).map((a: any, i: number) => (
                <Row key={i}>
                  <Cell mono>{(a.ts ?? "").slice(0, 19)}</Cell>
                  <Cell>{a.action}</Cell>
                  <Cell mono>{a.actor ?? "—"}</Cell>
                  <Cell>{a.role ?? "—"}</Cell>
                  <Cell>{a.approval_status ?? "—"}</Cell>
                  <Cell>{a.reason ?? "—"}</Cell>
                </Row>
              ))}
            </Table>
          </details>
        </Card>
      ))}
    </div>
  );
}
