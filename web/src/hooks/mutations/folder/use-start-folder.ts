import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { addFolderVideo, createFolder, updateFolder } from "@/api/folder";
import type { FolderCreateResponse } from "@/api/types";
import type { UseMutationCallback } from "@/hooks/types";

const MAX_FOLDER_NAME_LENGTH = 200;

function createDraftFolderName() {
  const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `새 영상 ${timestamp}-${suffix}`;
}

function uniqueTitleFallback(title: string, folderId: number) {
  const suffix = ` #${folderId}`;
  return `${title.slice(0, MAX_FOLDER_NAME_LENGTH - suffix.length)}${suffix}`;
}

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
      const folder = await createFolder(createDraftFolderName());
      const result = await addFolderVideo(folder.id, url, true);
      const title = result.video.title?.trim();
      if (title) {
        try {
          await updateFolder(folder.id, { name: title });
          return { ...folder, name: title };
        } catch (error) {
          if (error instanceof ApiError && error.status === 409) {
            const fallbackName = uniqueTitleFallback(title, folder.id);
            await updateFolder(folder.id, { name: fallbackName });
            return { ...folder, name: fallbackName };
          }
          throw error;
        }
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
