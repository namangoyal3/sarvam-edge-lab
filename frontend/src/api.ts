import { useEffect, useState, useCallback } from "react";

const LS_KEY = "sel-ui-state";
const LS_TOKEN = "sel-api-token";

// Share links like https://app/?token=xyz store the demo token once.
if (typeof window !== "undefined" && window.location.search.includes("token=")) {
  const t = new URLSearchParams(window.location.search).get("token");
  if (t) localStorage.setItem(LS_TOKEN, t);
}
export function apiToken(): string {
  return localStorage.getItem(LS_TOKEN) ?? "";
}

export const globalState = {
  role: localStorage.getItem(LS_KEY)
    ? JSON.parse(localStorage.getItem(LS_KEY)!).role || "admin"
    : "admin",
  tenant: localStorage.getItem(LS_KEY)
    ? JSON.parse(localStorage.getItem(LS_KEY)!).tenant || "t-acme"
    : "t-acme",
};

export function saveState() {
  localStorage.setItem(
    LS_KEY,
    JSON.stringify({ role: globalState.role, tenant: globalState.tenant })
  );
}

let refreshTick = 0;
const tickListeners = new Set<() => void>();
export function bumpRefresh() {
  refreshTick++;
  tickListeners.forEach((fn) => fn());
}
export function useRefreshTick() {
  const [t, setT] = useState(refreshTick);
  useEffect(() => {
    const fn = () => setT(refreshTick);
    tickListeners.add(fn);
    return () => void tickListeners.delete(fn);
  }, []);
  return t;
}

async function request(path: string, method = "GET", body?: unknown) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Demo-Role": globalState.role,
      "X-Tenant-ID": globalState.tenant,
      ...(apiToken() ? { "X-Demo-Token": apiToken() } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export function useApi<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const tick = useRefreshTick();
  const reload = useCallback(() => {
    if (!path) return;
    setLoading(true);
    request(path)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => reload(), [reload, tick]);
  return { data, error, loading, reload };
}

export const get = (p: string) => request(p);
export const post = (p: string, body?: unknown) => request(p, "POST", body ?? {});

// FormData variant (browser sets the multipart boundary itself).
export async function postForm(path: string, form: FormData) {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: {
      "X-Demo-Role": globalState.role,
      "X-Tenant-ID": globalState.tenant,
      ...(apiToken() ? { "X-Demo-Token": apiToken() } : {}),
    },
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}
