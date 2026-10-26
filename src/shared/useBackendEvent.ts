import { addEventListener, removeEventListener } from "@decky/api";
import { useEffect, useRef } from "react";

// Subscribe to a backend event for the life of a component.
export function useBackendEvent<T>(event: string, handler: (payload: T) => void): void {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const listener = addEventListener<[T]>(event, (payload) => ref.current(payload));
    return () => {
      removeEventListener(event, listener);
    };
  }, [event]);
}
