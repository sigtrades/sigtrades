import { useEffect, useState } from "react";
import { usersApi } from "@/api";

export type UserSearchHit = { id: string; email: string; display_name?: string | null };

const MIN_QUERY_LEN = 2;
const DEFAULT_DEBOUNCE_MS = 400;

export function useDebouncedUserSearch(
  query: string,
  enabled: boolean,
  debounceMs = DEFAULT_DEBOUNCE_MS,
) {
  const [hits, setHits] = useState<UserSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = query.trim();
  const canSearch = enabled && trimmed.length >= MIN_QUERY_LEN;

  useEffect(() => {
    if (!canSearch) {
      setHits([]);
      setSearching(false);
      setSearched(false);
      setError(null);
      return;
    }

    setSearching(true);
    setSearched(false);
    setError(null);

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const res = await usersApi.list(1, 10, trimmed);
        if (cancelled) return;
        setHits(
          (res.items || []).map((u: UserSearchHit) => ({
            id: u.id,
            email: u.email,
            display_name: u.display_name,
          })),
        );
      } catch {
        if (!cancelled) {
          setHits([]);
          setError("搜索失败，请稍后重试");
        }
      } finally {
        if (!cancelled) {
          setSearching(false);
          setSearched(true);
        }
      }
    }, debounceMs);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmed, canSearch, debounceMs]);

  return {
    hits,
    searching,
    searched,
    error,
    canSearch,
    minQueryLen: MIN_QUERY_LEN,
  };
}
