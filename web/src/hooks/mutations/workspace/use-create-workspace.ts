import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createWorkspace } from "@/api/workspace";
import type { UseMutationCallback } from "@/hooks/types";

export function useCreateWorkspace(callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createWorkspace,
    onSuccess: (workspace) => {
      // channels/videos는 folder-first 리팩터 이전 키라 더 이상 어떤 쿼리도 안 쓴다 — folders 계열로 교체.
      // removeQueries는 활성 쿼리를 자동으로 refetch하지 않아 새로고침 전까진 반영이 안 됐다 — invalidateQueries로 교체.
      queryClient.setQueryData(["workspace", "me"], workspace);
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      queryClient.invalidateQueries({ queryKey: ["folder-videos"] });
      queryClient.invalidateQueries({ queryKey: ["folder-candidates"] });
      queryClient.invalidateQueries({ queryKey: ["channel-sources"] });
      queryClient.invalidateQueries({ queryKey: ["chat", "history"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
