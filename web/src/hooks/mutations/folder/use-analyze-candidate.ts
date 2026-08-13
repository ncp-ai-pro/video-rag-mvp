import { useMutation, useQueryClient } from "@tanstack/react-query";

import { analyzeCandidate } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 수집 후보를 폴더 영상으로 편입하고 분석 job을 등록한다("분석 후 추가"). */
export function useAnalyzeCandidate(folderId: number | null, callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (candidateId: number) => {
      if (folderId === null) throw new Error("폴더가 선택되지 않았습니다.");
      return analyzeCandidate(folderId, candidateId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folder-videos", folderId] });
      queryClient.invalidateQueries({ queryKey: ["folder-candidates", folderId] });
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
