import { useState, useEffect, useCallback, useRef } from "react";
import type { AxiosResponse } from "axios";

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

interface UseApiReturn<T> extends UseApiState<T> {
  refetch: () => void;
}

/**
 * Generic hook for fetching data from the API.
 * Automatically fetches on mount and provides refetch capability.
 */
export function useApi<T>(
  fetcher: () => Promise<AxiosResponse<T>>,
  deps: unknown[] = []
): UseApiReturn<T> {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const fetch = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await fetcherRef.current();
      setState({ data: res.data, loading: false, error: null });
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "An unexpected error occurred";
      setState({ data: null, loading: false, error: msg });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { ...state, refetch: fetch };
}

/**
 * Hook for lazy API calls (mutations / on-demand fetches).
 * Does NOT auto-fetch on mount.
 */
export function useLazyApi<TArgs extends unknown[], TResult>(
  fetcher: (...args: TArgs) => Promise<AxiosResponse<TResult>>
) {
  const [state, setState] = useState<UseApiState<TResult>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(
    async (...args: TArgs) => {
      setState({ data: null, loading: true, error: null });
      try {
        const res = await fetcher(...args);
        setState({ data: res.data, loading: false, error: null });
        return res.data;
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "An unexpected error occurred";
        setState({ data: null, loading: false, error: msg });
        throw err;
      }
    },
    [fetcher]
  );

  return { ...state, execute };
}
