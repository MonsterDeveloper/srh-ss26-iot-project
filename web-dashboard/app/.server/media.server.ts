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
  const url = new URL(media.url);
  if (url.origin !== config.mediaOrigin)
    throw new Response("Invalid media origin", { status: 502 });
  return media;
}
