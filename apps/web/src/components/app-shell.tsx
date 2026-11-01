"use client";

import React from "react";
import { setToken } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Briefcase,
  LayoutDashboard,
  LogOut,
  Mail,
  Megaphone,
  Settings,
  Users,
  FileText,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const nav = [
  {
    section: "HR Recruitment",
    items: [
      { href: "/hr", label: "Inbox", icon: Mail },
      { href: "/hr/rules", label: "Compliance Rules", icon: ShieldCheck },
      { href: "/hr/pipeline", label: "Pipeline", icon: Workflow },
    ],
  },
  {
    section: "Campaigns",
    items: [
      { href: "/campaigns", label: "Campaigns", icon: Megaphone },
      { href: "/contacts", label: "Contacts", icon: Users },
      { href: "/templates", label: "Templates", icon: FileText },
    ],
  },
  {
    section: "System",
    items: [{ href: "/settings", label: "Settings", icon: Settings }],
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    setToken(null);
    router.push("/login");
  }

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="border-b border-white/10 px-5 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow-lg shadow-teal-900/30">
            <Briefcase className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wide">Email Replier</div>
            <div className="text-[11px] text-sidebar-muted">HR + Campaigns</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <Link
          href="/hr"
          className={cn(
            "mb-4 flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
            pathname === "/hr"
              ? "bg-white/10 text-white"
              : "text-sidebar-muted hover:bg-white/5 hover:text-white",
          )}
        >
          <LayoutDashboard className="h-4 w-4" />
          Overview
        </Link>

        {nav.map((group) => (
          <div key={group.section} className="mb-5">
            <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted">
              {group.section}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(item.href + "/");
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition",
                      active
                        ? "bg-accent text-white shadow-md shadow-teal-950/20"
                        : "text-sidebar-muted hover:bg-white/5 hover:text-white",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-white/10 p-3">
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-sidebar-muted transition hover:bg-white/5 hover:text-white"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    const token = localStorage.getItem("em_token");
    if (!token) {
      router.replace("/login");
      return;
    }
    api("/api/auth/me")
      .then(() => setReady(true))
      .catch(() => {
        setToken(null);
        router.replace("/login");
      });
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading workspace…
      </div>
    );
  }
  return <>{children}</>;
}
