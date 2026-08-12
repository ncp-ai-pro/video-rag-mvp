import { useQuery } from "@tanstack/react-query";

import { fetchMe } from "@/api/workspace";

export function useMe() {
  return useQuery({
    queryKey: ["workspace", "me"],
    queryFn: fetchMe,
  });
}
