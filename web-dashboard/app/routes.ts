import {
  type RouteConfig,
  index,
  layout,
  route,
} from "@react-router/dev/routes";

export default [
  route("login", "routes/login.tsx"),
  route("logout", "routes/logout.tsx"),
  route("health", "routes/health.tsx"),
  route("resources/locale", "routes/resources.locale.tsx"),
  layout("routes/protected-layout.tsx", [
    index("routes/overview.tsx"),
    route("experiments", "routes/experiments.tsx"),
    route("experiments/new", "routes/experiment-new.tsx"),
    route("experiments/:experimentId", "routes/experiment-detail.tsx"),
    route("experiments/:experimentId/edit", "routes/experiment-edit.tsx"),
    route("experiments/:experimentId/exercises/new", "routes/exercise-new.tsx"),
    route(
      "experiments/:experimentId/exercises/:exerciseId",
      "routes/exercise-detail.tsx",
    ),
    route("analysis", "routes/analysis.tsx"),
    route("quality", "routes/quality.tsx"),
    route("resources/analysis.csv", "routes/resources.analysis-csv.tsx"),
    route(
      "resources/experiments/:experimentId.csv",
      "routes/resources.experiment-csv.tsx",
    ),
    route(
      "resources/exercises/:exerciseId/media/:asset",
      "routes/resources.media.tsx",
    ),
  ]),
] satisfies RouteConfig;
