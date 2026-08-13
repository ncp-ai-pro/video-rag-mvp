import { useMutation, useQueryClient } from "@tanstack/react-query";

import { addFolderVideo, createFolder, updateFolder } from "@/api/folder";
import type { FolderCreateResponse } from "@/api/types";
import type { UseMutationCallback } from "@/hooks/types";

/**
 * 홈 화면 시작 흐름: URL 하나만 받는다. 폴더 이름을 먼저 물어보면 사용자가 뭘 적어야 할지
 * 몰라 어색해지므로, 임시 이름으로 폴더를 만들고 영상을 추가한 뒤 그 영상 제목으로 바로
 * 개명한다(folder-first-api-spec.md의 "폴더명 자동 추천" MVP 대안 — frontend heuristic).
 */
export function useStartFolder(
  callbacks?: UseMutationCallback & { onSettled?: (folder: FolderCreateResponse) => void },
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ url }: { url: string }) => {
      const folder = await createFolder("새 폴더");
      const result = await addFolderVideo(folder.id, url, true);
      const title = result.video.title?.trim();
      if (title) {
        await updateFolder(folder.id, { name: title });
        return { ...folder, name: title };
      }
      return folder;
    },
    onSuccess: (folder) => {
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      callbacks?.onSuccess?.();
      callbacks?.onSettled?.(folder);
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
