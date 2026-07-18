import { z } from "zod";

import { apiRequest } from "./api.server";
import { config } from "./config.server";

const linkSchema = z.object({
  url: z.string().url(),
  expiry: z.string(),
  filename: z.string(),
  contentType: z.string(),
  size: z.number().nullable(),
});

export async function getMediaRedirect(
  exerciseId: string,
  asset: string,
  actor: string,
) {
  const allowed = ["motion", "audio", "video_source", "video_playback"];
  if (!allowed.includes(asset))
    throw new Response("Not found", { status: 404 });
  const media = await apiRequest(
    `/exercises/${encodeURIComponent(exerciseId)}/media/${asset}/url`,
    {
      actor,
      schema: linkSchema,
    },
  );
  const sourceUrl = new URL(media.url);
  const url = new URL(
    `${sourceUrl.pathname}${sourceUrl.search}${sourceUrl.hash}`,
    config.mediaOrigin,
  );
  return { ...media, url: url.toString() };
}
