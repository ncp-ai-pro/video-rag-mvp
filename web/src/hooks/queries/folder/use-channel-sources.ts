import { useQuery } from "@tanstack/react-query";

import { fetchChannelSources } from "@/api/folder";

export function useChannelSources(folderId: number | null) {
  return useQuery({
    queryKey: ["channel-sources", folderId],
    queryFn: () => fetchChannelSources(folderId as number),
    enabled: folderId !== null,
  });
}
