import { useMutation, useQueryClient } from "@tanstack/react-query";

import { connectWorkspace } from "@/api/workspace";
import type { UseMutationCallback } from "@/hooks/types";

export function useConnectWorkspace(callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: connectWorkspace,
    onSuccess: (workspace) => {
      // 새 작업공간으로 전환된 것이므로 이전 작업공간의 캐시를 전부 비운다.
      queryClient.setQueryData(["workspace", "me"], workspace);
      queryClient.removeQueries({ queryKey: ["channels"] });
      queryClient.removeQueries({ queryKey: ["videos"] });
      queryClient.removeQueries({ queryKey: ["chat", "history"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
