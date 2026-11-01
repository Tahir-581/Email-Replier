"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, Card, Label, PageHeader } from "@/components/ui/primitives";
import { formatDate } from "@/lib/utils";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

type Campaign = {
  id: string;
  name: string;
  status: string;
  list_id?: string;
  template_id?: string;
  error?: string;
  sent_at?: string;
};

type Message = {
  id: string;
  to_email: string;
  subject?: string;
  status: string;
  error?: string;
  sent_at?: string;
  provider_id?: string;
};

type ListItem = { id: string; name: string };
type TemplateItem = { id: string; name: string };

export default function CampaignDetailPage() {
  const params = useParams();
  const id = String(params.id);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [lists, setLists] = useState<ListItem[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [detail, l, t] = await Promise.all([
      api<{ campaign: Campaign; messages: Message[] }>(`/api/campaigns/${id}`),
      api<{ items: ListItem[] }>("/api/lists"),
      api<{ items: TemplateItem[] }>("/api/templates"),
    ]);
    setCampaign(detail.campaign);
    setMessages(detail.messages);
    setLists(l.items);
    setTemplates(t.items);
  }, [id]);

  useEffect(() => {
    load().catch((e) => setMessage(e.message));
  }, [load]);

  async function updateField(patch: Partial<Campaign>) {
    if (!campaign) return;
    const updated = await api<Campaign>(`/api/campaigns/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    setCampaign(updated);
  }

  async function preview() {
    const data = await api<{ recipient_count: number }>(`/api/campaigns/${id}/preview`);
    setPreviewCount(data.recipient_count);
  }

  async function send() {
    setBusy(true);
    setMessage("");
    try {
      const res = await api<{ message: string }>(`/api/campaigns/${id}/send`, { method: "POST" });
      setMessage(res.message);
      setTimeout(() => load(), 1500);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  if (!campaign) {
    return <div className="text-sm text-muted-foreground">Loading campaign…</div>;
  }

  return (
    <div>
      <PageHeader
        title={campaign.name}
        description="Assign list & template, preview recipients, then send via Resend."
        actions={
          <>
            <Button variant="outline" onClick={preview}>
              Preview recipients
            </Button>
            <Button onClick={send} disabled={busy || campaign.status === "sending"}>
              {busy ? "Starting…" : "Send campaign"}
            </Button>
          </>
        }
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}
      {previewCount !== null ? (
        <div className="mb-4 text-sm text-muted-foreground">
          Recipients in list: <strong>{previewCount}</strong>
        </div>
      ) : null}

      <Card className="mb-6 grid gap-4 p-5 md:grid-cols-3">
        <div>
          <Label>Status</Label>
          <div className="mt-1">
            <Badge
              tone={
                campaign.status === "sent"
                  ? "success"
                  : campaign.status === "failed"
                    ? "danger"
                    : campaign.status === "sending"
                      ? "accent"
                      : "default"
              }
            >
              {campaign.status}
            </Badge>
          </div>
          {campaign.error ? <p className="mt-2 text-sm text-danger">{campaign.error}</p> : null}
          {campaign.sent_at ? (
            <p className="mt-2 text-xs text-muted-foreground">Sent {formatDate(campaign.sent_at)}</p>
          ) : null}
        </div>
        <div>
          <Label>List</Label>
          <select
            className="mt-1 h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
            value={campaign.list_id || ""}
            onChange={(e) => updateField({ list_id: e.target.value || undefined })}
            disabled={campaign.status === "sending"}
          >
            <option value="">Select list</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Template</Label>
          <select
            className="mt-1 h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
            value={campaign.template_id || ""}
            onChange={(e) => updateField({ template_id: e.target.value || undefined })}
            disabled={campaign.status === "sending"}
          >
            <option value="">Select template</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-border px-4 py-3 text-sm font-medium">
          Delivery status ({messages.length})
        </div>
        <div className="divide-y divide-border">
          {messages.map((m) => (
            <div key={m.id} className="px-4 py-3 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-medium">{m.to_email}</span>
                <Badge
                  tone={
                    m.status === "sent" ? "success" : m.status === "failed" ? "danger" : "warning"
                  }
                >
                  {m.status}
                </Badge>
              </div>
              <div className="text-muted-foreground">{m.subject}</div>
              {m.error ? <div className="text-danger">{m.error}</div> : null}
            </div>
          ))}
          {messages.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              No messages yet. Send the campaign to populate status.
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
