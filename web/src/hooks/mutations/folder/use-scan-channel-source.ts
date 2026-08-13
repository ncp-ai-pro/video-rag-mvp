import { useMutation, useQueryClient } from "@tanstack/react-query";

import { scanChannelSource } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 이미 연결된 채널 소스를 다시 스캔한다. */
export function useScanChannelSource(folderId: number | null, callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: number) => {
      if (folderId === null) throw new Error("폴더가 선택되지 않았습니다.");
      return scanChannelSource(folderId, sourceId);
    },
    onSuccess: () => {
      // last_scanned_at·candidate_count가 바뀌고, 새 후보도 생길 수 있어서 둘 다 갱신한다.
      queryClient.invalidateQueries({ queryKey: ["channel-sources", folderId] });
      queryClient.invalidateQueries({ queryKey: ["folder-candidates", folderId] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
