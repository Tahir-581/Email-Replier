"use client";

import { api, apiBlob } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Input, Label, PageHeader } from "@/components/ui/primitives";
import { Download, Plus, Upload } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Contact = {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  company?: string;
  address?: string;
};

type ContactList = {
  id: string;
  name: string;
  description?: string;
  member_count?: number;
};

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [lists, setLists] = useState<ContactList[]>([]);
  const [q, setQ] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    company: "",
    address: "",
  });
  const [listName, setListName] = useState("");

  const load = useCallback(async () => {
    const params = q ? `?q=${encodeURIComponent(q)}` : "";
    const [c, l] = await Promise.all([
      api<{ items: Contact[] }>(`/api/contacts${params}`),
      api<{ items: ContactList[] }>("/api/lists"),
    ]);
    setContacts(c.items);
    setLists(l.items);
  }, [q]);

  useEffect(() => {
    load().catch((e) => setMessage(e.message));
  }, [load]);

  async function createContact(e: FormEvent) {
    e.preventDefault();
    await api("/api/contacts", { method: "POST", body: JSON.stringify(form) });
    setForm({ email: "", first_name: "", last_name: "", company: "", address: "" });
    setMessage("Contact created.");
    await load();
  }

  async function createList(e: FormEvent) {
    e.preventDefault();
    await api("/api/lists", { method: "POST", body: JSON.stringify({ name: listName }) });
    setListName("");
    await load();
  }

  async function importCsv(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await api<{ created: number; skipped: number }>("/api/contacts/import", {
      method: "POST",
      formData: fd,
    });
    setMessage(`Imported ${res.created}, skipped ${res.skipped}.`);
    await load();
  }

  async function exportCsv() {
    const blob = await apiBlob("/api/contacts/export/csv");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "contacts_export.csv";
    a.click();
  }

  async function addAllToList(listId: string) {
    await api(`/api/lists/${listId}/members`, {
      method: "POST",
      body: JSON.stringify({ contact_ids: contacts.map((c) => c.id) }),
    });
    setMessage("Added visible contacts to list.");
    await load();
  }

  return (
    <div>
      <PageHeader
        title="Contacts"
        description="Manage recipients and lists for commercial campaigns."
        actions={
          <>
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-lg border border-border bg-card px-4 text-sm hover:bg-muted">
              <Upload className="h-4 w-4" /> Import CSV
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])}
              />
            </label>
            <Button variant="outline" onClick={exportCsv}>
              <Download className="h-4 w-4" /> Export
            </Button>
          </>
        }
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-1 space-y-4">
          <h2 className="font-semibold">Add contact</h2>
          <form onSubmit={createContact} className="space-y-3">
            {(
              [
                ["email", "Email"],
                ["first_name", "First name"],
                ["last_name", "Last name"],
                ["company", "Company"],
                ["address", "Address"],
              ] as const
            ).map(([key, label]) => (
              <div key={key}>
                <Label>{label}</Label>
                <Input
                  required={key === "email"}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
              </div>
            ))}
            <Button type="submit" className="w-full">
              <Plus className="h-4 w-4" /> Create
            </Button>
          </form>

          <form onSubmit={createList} className="space-y-3 border-t border-border pt-4">
            <h2 className="font-semibold">New list</h2>
            <Input
              placeholder="List name"
              value={listName}
              onChange={(e) => setListName(e.target.value)}
              required
            />
            <Button type="submit" variant="secondary" className="w-full">
              Create list
            </Button>
          </form>
        </Card>

        <div className="lg:col-span-2 space-y-4">
          <Input
            placeholder="Search contacts…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="max-w-sm"
          />
          <Card className="overflow-hidden">
            <div className="divide-y divide-border">
              {contacts.map((c) => (
                <div key={c.id} className="px-4 py-3">
                  <div className="font-medium">
                    {c.first_name} {c.last_name}{" "}
                    <span className="text-muted-foreground font-normal">{c.email}</span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {[c.company, c.address].filter(Boolean).join(" · ") || "—"}
                  </div>
                </div>
              ))}
              {contacts.length === 0 ? (
                <div className="px-4 py-10 text-center text-sm text-muted-foreground">
                  No contacts yet.
                </div>
              ) : null}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="mb-3 font-semibold">Lists</h2>
            <div className="space-y-2">
              {lists.map((l) => (
                <div
                  key={l.id}
                  className="flex items-center justify-between rounded-xl bg-muted/50 px-3 py-2"
                >
                  <div>
                    <div className="font-medium">{l.name}</div>
                    <div className="text-xs text-muted-foreground">{l.member_count || 0} members</div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => addAllToList(l.id)}>
                    Add visible
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
