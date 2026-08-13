import { useQuery } from "@tanstack/react-query";

import { fetchFolderVideos } from "@/api/folder";

export function useFolderVideos(folderId: number | null) {
  return useQuery({
    queryKey: ["folder-videos", folderId],
    queryFn: () => fetchFolderVideos(folderId as number),
    enabled: folderId !== null,
  });
}
