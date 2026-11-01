"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Input, Label, PageHeader, Textarea } from "@/components/ui/primitives";
import { useEffect, useState } from "react";

type Template = {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  body_text?: string;
};

const TAGS = ["first_name", "last_name", "full_name", "email", "company", "address"];

export default function TemplatesPage() {
  const [items, setItems] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Template | null>(null);
  const [preview, setPreview] = useState<{ subject: string; body_html: string } | null>(null);
  const [message, setMessage] = useState("");

  async function load() {
    const data = await api<{ items: Template[] }>("/api/templates");
    setItems(data.items);
  }

  useEffect(() => {
    load().catch((e) => setMessage(e.message));
  }, []);

  function newTemplate() {
    setSelected({
      id: "",
      name: "Untitled template",
      subject: "Hello {{first_name}}",
      body_html:
        "<p>Hi {{first_name}},</p><p>We're reaching out regarding an opportunity at our company.</p><p>Best regards</p>",
      body_text: "",
    });
    setPreview(null);
  }

  async function save() {
    if (!selected) return;
    if (selected.id) {
      await api(`/api/templates/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: selected.name,
          subject: selected.subject,
          body_html: selected.body_html,
          body_text: selected.body_text,
        }),
      });
    } else {
      await api("/api/templates", {
        method: "POST",
        body: JSON.stringify({
          name: selected.name,
          subject: selected.subject,
          body_html: selected.body_html,
          body_text: selected.body_text,
        }),
      });
    }
    setMessage("Template saved.");
    await load();
  }

  async function doPreview() {
    if (!selected) return;
    const data = await api<{ subject: string; body_html: string }>("/api/templates/preview", {
      method: "POST",
      body: JSON.stringify({
        subject: selected.subject,
        body_html: selected.body_html,
      }),
    });
    setPreview(data);
  }

  function insertTag(tag: string) {
    if (!selected) return;
    setSelected({ ...selected, body_html: `${selected.body_html}{{${tag}}}` });
  }

  return (
    <div>
      <PageHeader
        title="Templates"
        description="Compose campaign emails with dynamic merge tags."
        actions={<Button onClick={newTemplate}>New template</Button>}
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-1">
          <div className="divide-y divide-border">
            {items.map((t) => (
              <button
                key={t.id}
                className="block w-full px-4 py-3 text-left hover:bg-muted/60"
                onClick={() => {
                  setSelected(t);
                  setPreview(null);
                }}
              >
                <div className="font-medium">{t.name}</div>
                <div className="truncate text-sm text-muted-foreground">{t.subject}</div>
              </button>
            ))}
            {items.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                No templates yet.
              </div>
            ) : null}
          </div>
        </Card>

        <Card className="space-y-4 p-5 lg:col-span-2">
          {selected ? (
            <>
              <div>
                <Label>Name</Label>
                <Input
                  value={selected.name}
                  onChange={(e) => setSelected({ ...selected, name: e.target.value })}
                />
              </div>
              <div>
                <Label>Subject</Label>
                <Input
                  value={selected.subject}
                  onChange={(e) => setSelected({ ...selected, subject: e.target.value })}
                />
              </div>
              <div>
                <Label>HTML body</Label>
                <Textarea
                  className="min-h-[200px] font-mono text-xs"
                  value={selected.body_html}
                  onChange={(e) => setSelected({ ...selected, body_html: e.target.value })}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                {TAGS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => insertTag(tag)}
                    className="rounded-full bg-muted px-3 py-1 text-xs font-medium hover:bg-accent-soft"
                  >
                    {`{{${tag}}}`}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={doPreview}>
                  Preview
                </Button>
                <Button onClick={save}>Save</Button>
              </div>
              {preview ? (
                <div className="rounded-xl border border-border bg-muted/40 p-4">
                  <div className="mb-2 text-sm font-semibold">{preview.subject}</div>
                  <div
                    className="prose prose-sm max-w-none text-sm"
                    dangerouslySetInnerHTML={{ __html: preview.body_html }}
                  />
                </div>
              ) : null}
            </>
          ) : (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Select or create a template.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
