import { useMutation, useQueryClient } from "@tanstack/react-query";

import { addChannelSource } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 폴더에 채널 URL을 수집 소스로 연결한다(auto_scan이라 바로 스캔도 등록된다). */
export function useAddChannelSource(folderId: number | null, callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => {
      if (folderId === null) throw new Error("폴더가 선택되지 않았습니다.");
      return addChannelSource(folderId, url);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channel-sources", folderId] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
