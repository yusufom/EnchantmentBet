"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchPredictions, refreshPredictions, refreshResults } from "@/lib/api";
import type { SportFilter } from "@/lib/types";

export function predictionsKey(date: string, sport: SportFilter) {
  return ["predictions", date, sport] as const;
}

export function usePredictions(date: string, sport: SportFilter) {
  return useQuery({
    queryKey: predictionsKey(date, sport),
    queryFn: () => fetchPredictions(date, sport === "all" ? undefined : sport),
    staleTime: 60_000,
  });
}

export function useRefreshPredictions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ date, sport }: { date: string; sport: SportFilter }) =>
      refreshPredictions(date, sport === "all" ? undefined : sport),
    onSuccess: (data, { date, sport }) => {
      queryClient.setQueryData(predictionsKey(date, sport), data);
      // Only this date's queries are stale — other dates keep their cache,
      // mirroring the backend's date-scoped storage.
      queryClient.invalidateQueries({ queryKey: ["predictions", date] });
    },
  });
}

export function useRefreshResults() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ date, sport }: { date: string; sport: SportFilter }) =>
      refreshResults(date, sport === "all" ? undefined : sport),
    onSuccess: (data, { date, sport }) => {
      queryClient.setQueryData(predictionsKey(date, sport), data);
      queryClient.invalidateQueries({ queryKey: ["predictions", date] });
    },
  });
}
