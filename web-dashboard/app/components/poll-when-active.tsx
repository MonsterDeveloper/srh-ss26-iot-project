import { useEffect } from "react";
import { useRevalidator } from "react-router";

export function PollWhenActive({
  active,
  interval = 5000,
}: {
  active: boolean;
  interval?: number;
}) {
  const revalidator = useRevalidator();
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      if (
        document.visibilityState === "visible" &&
        revalidator.state === "idle"
      )
        revalidator.revalidate();
    }, interval);
    return () => window.clearInterval(timer);
  }, [active, interval, revalidator]);
  return null;
}
