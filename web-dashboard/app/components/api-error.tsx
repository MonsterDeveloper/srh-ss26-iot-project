import { AlertCircle, RotateCw } from "lucide-react";
import { useRevalidator } from "react-router";

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import { Button } from "~/components/ui/button";

export function ApiErrorState({
  title,
  message,
  retryLabel,
}: {
  title: string;
  message: string;
  retryLabel: string;
}) {
  const revalidator = useRevalidator();
  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex items-center justify-between gap-4">
        <span>{message}</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => revalidator.revalidate()}
          disabled={revalidator.state !== "idle"}
        >
          <RotateCw
            className={revalidator.state !== "idle" ? "animate-spin" : ""}
          />{" "}
          {retryLabel}
        </Button>
      </AlertDescription>
    </Alert>
  );
}
