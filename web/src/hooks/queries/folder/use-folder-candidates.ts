import { useQuery } from "@tanstack/react-query";

import { fetchFolderCandidates } from "@/api/folder";

export function useFolderCandidates(folderId: number | null) {
  return useQuery({
    queryKey: ["folder-candidates", folderId],
    queryFn: () => fetchFolderCandidates(folderId as number),
    enabled: folderId !== null,
  });
}
