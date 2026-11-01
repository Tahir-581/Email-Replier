"use client";

import { api, apiBlob } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Label, PageHeader, Textarea } from "@/components/ui/primitives";
import { Download, RefreshCw, Send, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type EmailItem = {
  id: string;
  email_id: string;
  subject?: string;
  from_addr?: string;
  status: string;
  created_at?: string;
  body?: string;
};

type Reply = {
  id: string;
  subject?: string;
  body?: string;
  intent_label?: string;
  profile_type?: string;
  sent_at?: string;
  detected_intents?: unknown;
};

export default function HrInboxPage() {
  const [items, setItems] = useState<EmailItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ email: EmailItem; replies: Reply[] } | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (q) params.set("q", q);
      const data = await api<{ total: number; items: EmailItem[] }>(
        `/api/hr/emails?${params.toString()}`,
      );
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [status, q]);

  useEffect(() => {
    load();
  }, [load]);

  async function openDetail(emailId: string) {
    setSelected(emailId);
    const data = await api<{ email: EmailItem; replies: Reply[] }>(`/api/hr/emails/${emailId}`);
    setDetail(data);
    const latest = data.replies[0];
    setEditSubject(latest?.subject || `Re: ${data.email.subject || ""}`);
    setEditBody(latest?.body || "");
  }

  async function saveAndSend(forceSend: boolean) {
    if (!detail?.replies[0]) {
      setMessage("No reply draft available yet. Run the pipeline first.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const replyId = detail.replies[0].id;
      await api(`/api/hr/replies/${replyId}`, {
        method: "PATCH",
        body: JSON.stringify({ subject: editSubject, body: editBody }),
      });
      const res = await api<{ mode: string }>(`/api/hr/replies/${replyId}/send`, {
        method: "POST",
        body: JSON.stringify({ force_send: forceSend }),
      });
      setMessage(res.mode === "sent" ? "Email sent via Gmail." : "Gmail draft created.");
      await openDetail(detail.email.email_id);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  async function reprocess() {
    if (!detail) return;
    setBusy(true);
    try {
      await api(`/api/hr/emails/${detail.email.email_id}/reprocess`, { method: "POST" });
      setMessage("Reprocess queued.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function exportReplies() {
    const blob = await apiBlob("/api/hr/export/replies");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "replies_export.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function statusTone(s: string) {
    if (s === "processed") return "success" as const;
    if (s === "pending") return "warning" as const;
    if (s === "error") return "danger" as const;
    if (s === "irrelevant") return "default" as const;
    return "accent" as const;
  }

  return (
    <div>
      <PageHeader
        title="HR Inbox"
        description="Review candidate emails and approve compliance-aware AI replies."
        actions={
          <>
            <Button variant="outline" onClick={exportReplies}>
              <Download className="h-4 w-4" /> Export replies
            </Button>
            <Button variant="secondary" onClick={load}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Input
          placeholder="Search subject, sender…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs"
        />
        <select
          className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="processed">Processed</option>
          <option value="irrelevant">Irrelevant</option>
          <option value="error">Error</option>
        </select>
      </div>

      {message ? (
        <div className="mb-4 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-accent-hover">
          {message}
        </div>
      ) : null}

      <Card className="overflow-hidden">
        <div className="border-b border-border px-4 py-3 text-sm text-muted-foreground">
          {loading ? "Loading…" : `${total} emails`}
        </div>
        <div className="divide-y divide-border">
          {items.map((item) => (
            <button
              key={item.id}
              onClick={() => openDetail(item.email_id)}
              className="flex w-full items-start gap-4 px-4 py-3 text-left transition hover:bg-muted/60"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{item.subject || "(no subject)"}</span>
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                </div>
                <div className="mt-1 truncate text-sm text-muted-foreground">
                  {item.from_addr} · {formatDate(item.created_at)}
                </div>
              </div>
            </button>
          ))}
          {!loading && items.length === 0 ? (
            <div className="px-4 py-12 text-center text-sm text-muted-foreground">
              No emails yet. Run the pipeline from HR → Pipeline.
            </div>
          ) : null}
        </div>
      </Card>

      {selected && detail ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm">
          <div className="flex h-full w-full max-w-xl flex-col bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 className="font-semibold">{detail.email.subject}</h2>
                <p className="text-sm text-muted-foreground">{detail.email.from_addr}</p>
              </div>
              <button onClick={() => setSelected(null)} className="rounded-lg p-2 hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto p-5">
              <div>
                <Label>Inbound body</Label>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl bg-muted/70 p-3 text-xs">
                  {detail.email.body || "—"}
                </pre>
              </div>
              {detail.replies[0] ? (
                <div className="flex flex-wrap gap-2">
                  <Badge tone="accent">{detail.replies[0].intent_label || "No intent"}</Badge>
                  {detail.replies[0].profile_type ? (
                    <Badge>{detail.replies[0].profile_type}</Badge>
                  ) : null}
                </div>
              ) : null}
              <div>
                <Label>Reply subject</Label>
                <Input value={editSubject} onChange={(e) => setEditSubject(e.target.value)} />
              </div>
              <div>
                <Label>Reply body</Label>
                <Textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  className="min-h-[220px]"
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 border-t border-border p-4">
              <Button variant="outline" onClick={reprocess} disabled={busy}>
                Regenerate
              </Button>
              <Button variant="secondary" onClick={() => saveAndSend(false)} disabled={busy}>
                Create draft
              </Button>
              <Button onClick={() => saveAndSend(true)} disabled={busy}>
                <Send className="h-4 w-4" /> Send now
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
