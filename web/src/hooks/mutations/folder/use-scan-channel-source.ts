import { useMutation } from "@tanstack/react-query";

import { scanChannelSource } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 이미 연결된 채널 소스를 다시 스캔한다. */
export function useScanChannelSource(folderId: number | null, callbacks?: UseMutationCallback) {
  return useMutation({
    mutationFn: (sourceId: number) => {
      if (folderId === null) throw new Error("폴더가 선택되지 않았습니다.");
      return scanChannelSource(folderId, sourceId);
    },
    onSuccess: () => callbacks?.onSuccess?.(),
    onError: (error) => callbacks?.onError?.(error),
  });
}
