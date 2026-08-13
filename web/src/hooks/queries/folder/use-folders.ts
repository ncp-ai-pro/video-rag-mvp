import { useQuery } from "@tanstack/react-query";

import { fetchFolders } from "@/api/folder";

export function useFolders() {
  return useQuery({
    queryKey: ["folders"],
    queryFn: fetchFolders,
  });
}
