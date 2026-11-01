"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Label, PageHeader } from "@/components/ui/primitives";
import { useEffect, useState } from "react";

type Settings = {
  resend_api_key_set: boolean;
  resend_from_email: string;
  recruiter_name: string;
  recruiter_email: string;
  recruiter_title: string;
  company_name: string;
  company_website: string;
  linkedin_url: string;
  work_location: string;
  send_emails_directly: boolean;
  form_urls: Record<string, string>;
  llm_base_url: string;
  llm_model: string;
  gmail_connected: boolean;
  gmail_token_file: string;
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [resendKey, setResendKey] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<Settings>("/api/settings").then(setSettings).catch((e) => setMessage(e.message));
  }, []);

  async function save() {
    if (!settings) return;
    setSaving(true);
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        resend_from_email: settings.resend_from_email,
        recruiter_name: settings.recruiter_name,
        recruiter_email: settings.recruiter_email,
        recruiter_title: settings.recruiter_title,
        company_name: settings.company_name,
        company_website: settings.company_website,
        linkedin_url: settings.linkedin_url,
        work_location: settings.work_location,
        send_emails_directly: settings.send_emails_directly,
        form_urls: settings.form_urls,
        llm_base_url: settings.llm_base_url,
        llm_model: settings.llm_model,
      };
      if (resendKey.trim()) payload.resend_api_key = resendKey.trim();
      const updated = await api<Settings>("/api/settings", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setSettings(updated);
      setResendKey("");
      setMessage("Settings saved.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return <div className="text-sm text-muted-foreground">Loading settings…</div>;
  }

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Credentials, branding, and delivery configuration."
        actions={
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </Button>
        }
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">Email providers</h2>
          <div className="flex items-center gap-2 text-sm">
            Gmail (HR replies):{" "}
            <Badge tone={settings.gmail_connected ? "success" : "warning"}>
              {settings.gmail_connected ? "Connected" : "Not connected"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Token file: {settings.gmail_token_file}. Run{" "}
            <code className="rounded bg-muted px-1">python scripts/setup_gmail_oauth.py</code> to
            connect.
          </p>
          <div>
            <Label>Resend API key {settings.resend_api_key_set ? "(set)" : "(not set)"}</Label>
            <Input
              type="password"
              placeholder={settings.resend_api_key_set ? "•••••••• (leave blank to keep)" : "re_…"}
              value={resendKey}
              onChange={(e) => setResendKey(e.target.value)}
            />
          </div>
          <div>
            <Label>Resend from email</Label>
            <Input
              value={settings.resend_from_email}
              onChange={(e) => setSettings({ ...settings, resend_from_email: e.target.value })}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.send_emails_directly}
              onChange={(e) =>
                setSettings({ ...settings, send_emails_directly: e.target.checked })
              }
            />
            HR: send emails directly (else Gmail drafts)
          </label>
        </Card>

        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">Recruiter branding</h2>
          {(
            [
              ["recruiter_name", "Name"],
              ["recruiter_email", "Email"],
              ["recruiter_title", "Title"],
              ["company_name", "Company"],
              ["company_website", "Website"],
              ["linkedin_url", "LinkedIn"],
              ["work_location", "Location"],
            ] as const
          ).map(([key, label]) => (
            <div key={key}>
              <Label>{label}</Label>
              <Input
                value={settings[key]}
                onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
              />
            </div>
          ))}
        </Card>

        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">LLM</h2>
          <div>
            <Label>Base URL</Label>
            <Input
              value={settings.llm_base_url}
              onChange={(e) => setSettings({ ...settings, llm_base_url: e.target.value })}
            />
          </div>
          <div>
            <Label>Model</Label>
            <Input
              value={settings.llm_model}
              onChange={(e) => setSettings({ ...settings, llm_model: e.target.value })}
            />
          </div>
        </Card>

        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">Form URLs</h2>
          {Object.entries(settings.form_urls).map(([key, value]) => (
            <div key={key}>
              <Label>{key}</Label>
              <Input
                value={value}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    form_urls: { ...settings.form_urls, [key]: e.target.value },
                  })
                }
              />
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}
