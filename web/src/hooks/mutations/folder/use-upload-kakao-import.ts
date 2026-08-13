import { useMutation, useQueryClient } from "@tanstack/react-query";

import { uploadKakaoExport } from "@/api/folder";
import type { KakaoImportPriority, KakaoImportResponse } from "@/api/types";
import type { UseMutationCallback } from "@/hooks/types";

/** 카카오톡 채팅 내보내기(.txt) 업로드. 성공하면 폴더 영상·목록 캐시를 갱신한다. */
export function useUploadKakaoImport(
  folderId: number | null,
  callbacks?: UseMutationCallback & { onSettled?: (result: KakaoImportResponse) => void },
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, analyze, priority }: { file: File; analyze?: boolean; priority?: KakaoImportPriority }) => {
      if (folderId === null) throw new Error("폴더가 선택되지 않았습니다.");
      return uploadKakaoExport(folderId, file, { analyze, priority });
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["folder-videos", folderId] });
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
      callbacks?.onSettled?.(result);
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
