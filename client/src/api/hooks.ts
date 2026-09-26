import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { AppSettings, Guild, Item, OllamaModel, Status, TestResult, Watch } from "./types";

// Everything the inbox shows is refreshed on this cadence; the classifier
// batches every ~45s, so polling faster than this buys nothing.
export const POLL_MS = 15_000;

// Items

export type ItemFilter = "attention" | "all";

export function useItems(filter: ItemFilter, watchId: number | null) {
  const params = new URLSearchParams({ filter });
  if (watchId !== null) params.set("watch_id", String(watchId));
  return useQuery({
    queryKey: ["items", filter, watchId],
    queryFn: () => api.get<Item[]>(`/items?${params}`),
    refetchInterval: POLL_MS,
  });
}

function useInvalidateItems() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["items"] });
    qc.invalidateQueries({ queryKey: ["status"] });
    qc.invalidateQueries({ queryKey: ["watches"] });
  };
}

type ItemUpdate = { id: number; seen?: boolean; dismissed?: boolean };

export function useUpdateItem() {
  const qc = useQueryClient();
  const invalidate = useInvalidateItems();
  return useMutation({
    mutationFn: ({ id, ...payload }: ItemUpdate) => api.patch<Item>(`/items/${id}`, payload),
    // Optimistic: "Done" removes the tile immediately so the next one slides
    // under the mouse for rapid click-through, instead of waiting a round
    // trip plus refetch. Rolled back if the request fails.
    onMutate: async ({ id, seen, dismissed }: ItemUpdate) => {
      await qc.cancelQueries({ queryKey: ["items"] });
      const snapshot = qc.getQueriesData<Item[]>({ queryKey: ["items"] });
      const now = new Date().toISOString();
      qc.setQueriesData<Item[]>({ queryKey: ["items"] }, (old) => {
        if (!old) return old;
        if (dismissed) return old.filter((i) => i.id !== id);
        if (seen) return old.map((i) => (i.id === id && !i.seen_at ? { ...i, seen_at: now } : i));
        return old;
      });
      return { snapshot };
    },
    onError: (_err, _vars, ctx) => ctx?.snapshot.forEach(([key, data]) => qc.setQueryData(key, data)),
    onSettled: invalidate,
  });
}

export function useMarkAllSeen() {
  const invalidate = useInvalidateItems();
  return useMutation({
    mutationFn: ({ filter, watchId }: { filter: ItemFilter; watchId: number | null }) => {
      const params = new URLSearchParams({ filter });
      if (watchId !== null) params.set("watch_id", String(watchId));
      return api.post<{ updated: number }>(`/items/mark_all_seen?${params}`);
    },
    onSuccess: invalidate,
  });
}

export function useReclassifyItem() {
  const invalidate = useInvalidateItems();
  return useMutation({
    mutationFn: (id: number) => api.post<Item>(`/items/${id}/reclassify`),
    onSuccess: invalidate,
  });
}

// Watches

export function useWatches() {
  return useQuery({ queryKey: ["watches"], queryFn: () => api.get<Watch[]>("/watches"), refetchInterval: POLL_MS });
}

export function useCreateWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { channel_id?: string; guild_id?: string; criteria?: string }) =>
      api.post<Watch>("/watches", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watches"] });
      qc.invalidateQueries({ queryKey: ["channels"] });
    },
  });
}

export function useUpdateWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: {
      id: number;
      label?: string;
      criteria?: string;
      enabled?: boolean;
      always_catch_up?: boolean;
      excluded_channel_ids?: string[];
      excluded_category_ids?: string[];
    }) =>
      api.patch<Watch>(`/watches/${id}`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watches"] }),
  });
}

export function useDeleteWatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/watches/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watches"] });
      qc.invalidateQueries({ queryKey: ["channels"] });
      qc.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useTestWatch() {
  return useMutation({ mutationFn: (id: number) => api.post<TestResult[]>(`/watches/${id}/test`) });
}

export function useReclassifyWatch() {
  const invalidate = useInvalidateItems();
  return useMutation({
    mutationFn: (id: number) => api.post<{ queued: number }>(`/watches/${id}/reclassify`),
    onSuccess: invalidate,
  });
}

export function useChannels(enabled: boolean) {
  return useQuery({ queryKey: ["channels"], queryFn: () => api.get<Guild[]>("/discord/channels"), enabled });
}

// Settings / status

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: () => api.get<AppSettings>("/settings") });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<AppSettings>) => api.patch<AppSettings>("/settings", payload),
    onSuccess: (data) => qc.setQueryData(["settings"], data),
  });
}

export function useOllamaModels() {
  return useQuery({ queryKey: ["ollama-models"], queryFn: () => api.get<OllamaModel[]>("/settings/ollama-models") });
}

export function useStatus() {
  return useQuery({ queryKey: ["status"], queryFn: () => api.get<Status>("/status"), refetchInterval: POLL_MS });
}
