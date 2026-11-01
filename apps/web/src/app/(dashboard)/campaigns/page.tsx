"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Label, PageHeader } from "@/components/ui/primitives";
import { formatDate } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useState } from "react";

type Campaign = {
  id: string;
  name: string;
  status: string;
  list_id?: string;
  template_id?: string;
  message_count?: number;
  sent_count?: number;
  created_at?: string;
};

type ListItem = { id: string; name: string };
type TemplateItem = { id: string; name: string };

export default function CampaignsPage() {
  const [items, setItems] = useState<Campaign[]>([]);
  const [lists, setLists] = useState<ListItem[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [name, setName] = useState("");
  const [listId, setListId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const [c, l, t] = await Promise.all([
      api<{ items: Campaign[] }>("/api/campaigns"),
      api<{ items: ListItem[] }>("/api/lists"),
      api<{ items: TemplateItem[] }>("/api/templates"),
    ]);
    setItems(c.items);
    setLists(l.items);
    setTemplates(t.items);
  }

  useEffect(() => {
    load().catch((e) => setMessage(e.message));
  }, []);

  async function create() {
    const created = await api<Campaign>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify({
        name,
        list_id: listId || null,
        template_id: templateId || null,
      }),
    });
    setName("");
    setMessage("Campaign created.");
    await load();
    window.location.href = `/campaigns/${created.id}`;
  }

  function tone(status: string) {
    if (status === "sent") return "success" as const;
    if (status === "sending") return "accent" as const;
    if (status === "failed") return "danger" as const;
    return "default" as const;
  }

  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="Compose and send professional bulk emails via Resend."
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}

      <Card className="mb-6 grid gap-3 p-5 md:grid-cols-4">
        <div className="md:col-span-1">
          <Label>Campaign name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 outreach" />
        </div>
        <div>
          <Label>List</Label>
          <select
            className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
            value={listId}
            onChange={(e) => setListId(e.target.value)}
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
            className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
          >
            <option value="">Select template</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <Button className="w-full" onClick={create} disabled={!name}>
            Create campaign
          </Button>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="divide-y divide-border">
          {items.map((c) => (
            <Link
              key={c.id}
              href={`/campaigns/${c.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-muted/50"
            >
              <div>
                <div className="flex items-center gap-2 font-medium">
                  {c.name} <Badge tone={tone(c.status)}>{c.status}</Badge>
                </div>
                <div className="text-sm text-muted-foreground">
                  {c.sent_count || 0}/{c.message_count || 0} sent · {formatDate(c.created_at)}
                </div>
              </div>
            </Link>
          ))}
          {items.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              No campaigns yet.
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
