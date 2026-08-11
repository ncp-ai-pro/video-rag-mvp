import { useQuery } from "@tanstack/react-query";

import { fetchVideos } from "@/api/video";

export function useVideos(channelId: number | null) {
  return useQuery({
    queryKey: ["videos", channelId],
    queryFn: () => fetchVideos(channelId as number),
    enabled: channelId !== null,
  });
}
