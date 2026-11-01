"use client";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, PageHeader } from "@/components/ui/primitives";
import { Play, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Stats = {
  pending: number;
  processing: number;
  processed: number;
  irrelevant: number;
  error: number;
  total: number;
  replies: number;
};

export default function PipelinePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const data = await api<Stats>("/api/hr/pipeline/stats");
    setStats(data);
  }, []);

  useEffect(() => {
    load().catch((e) => setMessage(e.message));
  }, [load]);

  async function run(skipPull: boolean) {
    setBusy(true);
    setMessage("");
    try {
      const res = await api<{ message: string }>("/api/hr/pipeline/run", {
        method: "POST",
        body: JSON.stringify({ skip_pull: skipPull, limit: 20 }),
      });
      setMessage(res.message);
      setTimeout(() => load(), 2000);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  const tiles = stats
    ? [
        { label: "Pending", value: stats.pending },
        { label: "Processed", value: stats.processed },
        { label: "Irrelevant", value: stats.irrelevant },
        { label: "Errors", value: stats.error },
        { label: "Replies", value: stats.replies },
        { label: "Total emails", value: stats.total },
      ]
    : [];

  return (
    <div>
      <PageHeader
        title="Pipeline"
        description="Pull Gmail threads and run the LangGraph compliance reply engine."
        actions={
          <>
            <Button variant="outline" onClick={() => load()}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => run(true)}>
              Process pending
            </Button>
            <Button disabled={busy} onClick={() => run(false)}>
              <Play className="h-4 w-4" /> Pull + process
            </Button>
          </>
        }
      />
      {message ? (
        <div className="mb-4 rounded-xl bg-accent-soft px-4 py-3 text-sm text-accent-hover">{message}</div>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t) => (
          <Card key={t.label} className="p-5">
            <div className="text-sm text-muted-foreground">{t.label}</div>
            <div className="mt-2 text-3xl font-semibold tracking-tight">{t.value}</div>
          </Card>
        ))}
      </div>
    </div>
  );
}
