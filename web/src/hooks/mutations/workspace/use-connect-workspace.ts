import { useMutation, useQueryClient } from "@tanstack/react-query";

import { connectWorkspace } from "@/api/workspace";
import type { UseMutationCallback } from "@/hooks/types";

export function useConnectWorkspace(callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: connectWorkspace,
    onSuccess: (workspace) => {
      // 새 작업공간으로 전환된 것이므로 이전 작업공간의 캐시를 무효화한다.
      // (channels/videos는 folder-first 리팩터 이전 키라 더 이상 어떤 쿼리도 안 쓴다 — folders 계열로 교체)
      //
      // removeQueries는 캐시만 지울 뿐 화면에 붙어있는 활성 쿼리(예: IndexPage의 useFolders)를
      // 자동으로 다시 fetch하지 않는다 — 새로고침 전까진 빈 화면/이전 데이터인 채로 멈춰 있었다.
      // invalidateQueries는 무효화와 동시에 활성 쿼리를 즉시 refetch해서 새로고침 없이 반영된다.
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
