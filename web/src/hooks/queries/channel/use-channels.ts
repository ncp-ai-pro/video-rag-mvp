import { useQuery } from "@tanstack/react-query";

import { fetchChannels } from "@/api/channel";

export function useChannels() {
  return useQuery({
    queryKey: ["channels"],
    queryFn: fetchChannels,
  });
}
