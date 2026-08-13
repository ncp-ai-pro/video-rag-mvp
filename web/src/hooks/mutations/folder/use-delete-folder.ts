import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteFolder } from "@/api/folder";
import type { UseMutationCallback } from "@/hooks/types";

/** 폴더를 삭제한다. 되돌릴 수 없어서 호출 쪽에서 확인(confirm)을 받고 호출해야 한다. */
export function useDeleteFolder(callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (folderId: number) => deleteFolder(folderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
