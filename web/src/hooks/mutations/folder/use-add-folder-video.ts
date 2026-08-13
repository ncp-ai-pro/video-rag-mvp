import { useMutation, useQueryClient } from "@tanstack/react-query";

import { addFolderVideo } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 폴더에 영상 URL을 직접 추가하고 바로 분석 job도 등록한다. */
export function useAddFolderVideo(folderId: number | null, callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => {
      if (folderId === null) throw new Error("폴더가 선택되지 않았습니다.");
      return addFolderVideo(folderId, url);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-videos", folderId] });
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
