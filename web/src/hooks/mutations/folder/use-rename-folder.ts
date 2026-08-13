import { useMutation, useQueryClient } from "@tanstack/react-query";

import { updateFolder } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 폴더 이름을 바꾼다. 사이드바 "이름 바꾸기" 메뉴에서 쓴다. */
export function useRenameFolder(callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, name }: { folderId: number; name: string }) =>
      updateFolder(folderId, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
