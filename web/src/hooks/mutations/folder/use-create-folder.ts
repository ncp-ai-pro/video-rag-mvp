import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createFolder } from "@/api/folder";
import type { FolderCreateResponse } from "@/api/types";
import type { UseMutationCallback } from "@/hooks/types";

/** 폴더를 이름만으로 만든다(URL 불필요). 영상은 만든 뒤 폴더 안 "영상 추가"에서 넣는다. */
export function useCreateFolder(
  callbacks?: UseMutationCallback & { onSettled?: (folder: FolderCreateResponse) => void },
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createFolder(name),
    onSuccess: (folder) => {
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
      callbacks?.onSettled?.(folder);
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
