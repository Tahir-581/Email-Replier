"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Input, Label, PageHeader } from "@/components/ui/primitives";
import { useEffect, useState } from "react";

type Rules = {
  form_urls: Record<string, string>;
  send_emails_directly: boolean;
  recruiter_name: string;
  recruiter_email: string;
  recruiter_title: string;
  company_name: string;
  company_website: string;
  linkedin_url: string;
  work_location: string;
  intents: { id: number; label: string }[];
  notes: string;
};

export default function HrRulesPage() {
  const [rules, setRules] = useState<Rules | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<Rules>("/api/hr/rules").then(setRules).catch((e) => setMessage(String(e.message)));
  }, []);

  async function save() {
    if (!rules) return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await api<Rules>("/api/hr/rules", {
        method: "PUT",
        body: JSON.stringify({
          form_urls: rules.form_urls,
          send_emails_directly: rules.send_emails_directly,
          recruiter_name: rules.recruiter_name,
          recruiter_email: rules.recruiter_email,
          recruiter_title: rules.recruiter_title,
          company_name: rules.company_name,
          company_website: rules.company_website,
          linkedin_url: rules.linkedin_url,
          work_location: rules.work_location,
        }),
      });
      setRules(updated);
      setMessage("Rules saved.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!rules) {
    return <div className="text-sm text-muted-foreground">Loading rules…</div>;
  }

  return (
    <div>
      <PageHeader
        title="Compliance Rules"
        description="Operational knobs for recruiting replies. LLM policy prompts stay code-owned."
        actions={
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save rules"}
          </Button>
        }
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5 space-y-4">
          <h2 className="font-semibold">Branding & send mode</h2>
          {(
            [
              ["recruiter_name", "Recruiter name"],
              ["recruiter_email", "Recruiter email"],
              ["recruiter_title", "Title"],
              ["company_name", "Company"],
              ["company_website", "Website"],
              ["linkedin_url", "LinkedIn"],
              ["work_location", "Work location"],
            ] as const
          ).map(([key, label]) => (
            <div key={key}>
              <Label>{label}</Label>
              <Input
                value={rules[key]}
                onChange={(e) => setRules({ ...rules, [key]: e.target.value })}
              />
            </div>
          ))}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={rules.send_emails_directly}
              onChange={(e) => setRules({ ...rules, send_emails_directly: e.target.checked })}
            />
            Send emails directly (otherwise create Gmail drafts)
          </label>
        </Card>

        <Card className="p-5 space-y-4">
          <h2 className="font-semibold">Google Form URLs</h2>
          {Object.entries(rules.form_urls).map(([key, value]) => (
            <div key={key}>
              <Label>{key}</Label>
              <Input
                value={value}
                onChange={(e) =>
                  setRules({
                    ...rules,
                    form_urls: { ...rules.form_urls, [key]: e.target.value },
                  })
                }
              />
            </div>
          ))}
        </Card>
      </div>

      <Card className="mt-6 p-5">
        <h2 className="mb-3 font-semibold">Intent reference (1–28)</h2>
        <p className="mb-4 text-sm text-muted-foreground">{rules.notes}</p>
        <div className="grid gap-2 md:grid-cols-2">
          {rules.intents.map((intent) => (
            <div key={intent.id} className="rounded-lg bg-muted/60 px-3 py-2 text-sm">
              <span className="font-medium text-accent-hover">{intent.id}.</span> {intent.label}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
