import { LockKeyhole } from "lucide-react";
import { Form, redirect, useNavigation } from "react-router";

import { authenticator, LoginError } from "~/.server/auth.server";
import {
  createUserSession,
  getSessionUser,
  safeReturnTo,
} from "~/.server/session.server";
import { Alert, AlertDescription } from "~/components/ui/alert";
import { Button } from "~/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { dictionaries, getLocale } from "~/lib/i18n";
import type { Route } from "./+types/login";

export async function loader({ request }: Route.LoaderArgs) {
  if (await getSessionUser(request)) throw redirect("/");
  const url = new URL(request.url);
  return {
    locale: await getLocale(request),
    returnTo: safeReturnTo(url.searchParams.get("returnTo")),
  };
}

export async function action({ request }: Route.ActionArgs) {
  const form = await request.clone().formData();
  const returnTo = safeReturnTo(form.get("returnTo"));
  try {
    const user = await authenticator.authenticate("form", request);
    return createUserSession(request, user, returnTo);
  } catch (error) {
    const locale = await getLocale(request);
    if (error instanceof LoginError)
      return { error: error.code, locale, returnTo };
    throw error;
  }
}

export default function Login({
  loaderData,
  actionData,
}: Route.ComponentProps) {
  const locale = actionData?.locale ?? loaderData.locale;
  const d = dictionaries[locale];
  const navigation = useNavigation();
  return (
    <main className="grid min-h-screen grid-cols-[minmax(480px,42%)_1fr] bg-white">
      <section className="flex items-center justify-center p-12">
        <Card className="w-full max-w-md border-0 shadow-none">
          <CardHeader className="px-0">
            <div className="mb-6 grid size-11 place-items-center rounded-xl bg-blue-700 text-white">
              <LockKeyhole className="size-5" />
            </div>
            <CardTitle className="text-2xl">{d.auth.title}</CardTitle>
            <CardDescription>{d.auth.subtitle}</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Form method="post" className="space-y-5">
              <input
                type="hidden"
                name="returnTo"
                value={actionData?.returnTo ?? loaderData.returnTo}
              />
              {actionData?.error ? (
                <Alert variant="destructive">
                  <AlertDescription>
                    {actionData.error === "limited"
                      ? d.auth.limited
                      : d.auth.invalid}
                  </AlertDescription>
                </Alert>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="username">{d.auth.username}</Label>
                <Input
                  id="username"
                  name="username"
                  autoComplete="username"
                  autoCapitalize="none"
                  required
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">{d.auth.password}</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </div>
              <Button
                type="submit"
                size="lg"
                className="w-full"
                disabled={navigation.state !== "idle"}
              >
                {d.auth.submit}
              </Button>
            </Form>
          </CardContent>
        </Card>
      </section>
      <section className="relative overflow-hidden bg-blue-950 p-12 text-white">
        <div
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, white 1px, transparent 0)",
            backgroundSize: "28px 28px",
          }}
        />
        <div className="relative flex h-full flex-col justify-between">
          <div className="text-sm font-semibold tracking-wide">
            SRH · IoT & AI
          </div>
          <div className="max-w-xl">
            <p className="text-sm uppercase tracking-[0.2em] text-blue-300">
              Parkinson research console
            </p>
            <h1 className="mt-4 text-5xl font-semibold leading-tight">
              Movement, stability and voice—seen together.
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-blue-100/80">
              A focused workspace for reviewing multimodal gait, voice, and
              facial movement observations.
            </p>
          </div>
          <p className="text-xs text-blue-200/60">
            Authorized researchers only · All mutations are audited
          </p>
        </div>
      </section>
    </main>
  );
}
