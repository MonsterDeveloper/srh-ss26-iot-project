import {
  FlaskConical,
  Languages,
  LayoutDashboard,
  LogOut,
  Microscope,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import {
  createContext,
  Form,
  NavLink,
  Outlet,
  useLocation,
  useOutletContext,
} from "react-router";

import { apiRequest } from "~/.server/api.server";
import { privateHeaders } from "~/.server/headers.server";
import { requireSessionUser, type SessionUser } from "~/.server/session.server";
import { Button } from "~/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu";
import { metadataSchema, type Metadata } from "~/lib/domain";
import {
  dictionaries,
  getLocale,
  type Dictionary,
  type Locale,
} from "~/lib/i18n";
import type { Route } from "./+types/protected-layout";

export type DashboardContext = {
  user: SessionUser;
  locale: Locale;
  dictionary: Dictionary;
  metadata: Metadata | null;
  metadataError: boolean;
};
export function useDashboard() {
  return useOutletContext<DashboardContext>();
}
export const researcherContext = createContext<SessionUser>();
export const middleware: Route.MiddlewareFunction[] = [
  async ({ request, context }, next) => {
    context.set(researcherContext, await requireSessionUser(request));
    return next();
  },
];

export async function loader({ request, context }: Route.LoaderArgs) {
  const user = context.get(researcherContext);
  const locale = await getLocale(request);
  try {
    const metadata = await apiRequest("/dashboard/metadata", {
      actor: user.username,
      schema: metadataSchema,
    });
    return { user, locale, metadata, metadataError: false };
  } catch {
    return { user, locale, metadata: null, metadataError: true };
  }
}
export const headers = () => privateHeaders;

const navIcons = [LayoutDashboard, FlaskConical, Microscope, ShieldCheck];

export default function ProtectedLayout({ loaderData }: Route.ComponentProps) {
  const { user, locale, metadata, metadataError } = loaderData;
  const d = dictionaries[locale];
  const location = useLocation();
  const nav = [
    { to: "/", label: d.nav.overview },
    { to: "/experiments", label: d.nav.experiments },
    { to: "/analysis", label: d.nav.analysis },
    { to: "/quality", label: d.nav.quality },
  ];
  const current = [...nav]
    .reverse()
    .find((item) =>
      item.to === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(item.to),
    );
  return (
    <>
      <div className="desktop-required min-h-screen items-center justify-center p-8 text-center text-sm text-muted-foreground">
        {d.desktopRequired}
      </div>
      <div className="dashboard-shell min-h-screen pl-64">
        <aside className="fixed inset-y-0 left-0 z-20 flex w-64 flex-col border-r bg-white">
          <div className="flex h-16 items-center gap-3 border-b px-5">
            <div className="grid size-9 place-items-center rounded-lg bg-blue-700 text-white">
              <ActivityMark />
            </div>
            <div>
              <div className="text-sm font-semibold">SRH IoT</div>
              <div className="text-xs text-muted-foreground">{d.appName}</div>
            </div>
          </div>
          <nav className="flex-1 space-y-1 p-3">
            {nav.map((item, index) => {
              const Icon = navIcons[index];
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${isActive ? "bg-blue-50 text-blue-800" : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-950"}`
                  }
                >
                  <Icon className="size-4" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
          <div className="border-t p-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-emerald-500" />
              Research console
            </div>
            <p className="mt-2">Descriptive analysis only</p>
          </div>
        </aside>
        <div className="min-h-screen">
          <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b bg-white/95 px-8 backdrop-blur">
            <div className="text-sm text-muted-foreground">
              <span>{d.appName}</span>
              <span className="mx-2">/</span>
              <span className="font-medium text-foreground">
                {current?.label}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Form method="post" action="/resources/locale">
                <input
                  type="hidden"
                  name="locale"
                  value={locale === "en" ? "de" : "en"}
                />
                <input
                  type="hidden"
                  name="returnTo"
                  value={`${location.pathname}${location.search}`}
                />
                <Button type="submit" variant="ghost" size="sm">
                  <Languages />
                  {locale === "en" ? "DE" : "EN"}
                </Button>
              </Form>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={<Button variant="outline" size="sm" />}
                >
                  <UserRound />
                  {user.displayName}
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <div className="px-2 py-1.5 text-xs text-muted-foreground">
                    @{user.username}
                  </div>
                  <Form method="post" action="/logout">
                    <button
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                      type="submit"
                    >
                      <LogOut className="size-4" />
                      {d.auth.logout}
                    </button>
                  </Form>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </header>
          <main className="p-8">
            <Outlet
              context={
                {
                  user,
                  locale,
                  dictionary: d,
                  metadata,
                  metadataError,
                } satisfies DashboardContext
              }
            />
          </main>
        </div>
      </div>
    </>
  );
}

function ActivityMark() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="M3 12h4l2-6 4 12 2-6h6" />
    </svg>
  );
}
