import { useInfiniteQuery } from "@tanstack/react-query";

import { fetchFolderChatHistory } from "@/api/chat";

const PAGE_SIZE = 20;

/**
 * 선택한 폴더(및 영상이 있으면 그 영상)의 대화 기록을 최신 페이지부터 커서(before_id)로
 * 거슬러 올라가며 불러온다. videoId가 없으면 폴더 전체 대화를 가져온다.
 * data.pages[0]가 가장 최신 페이지이므로, 화면에 오래된→최신 순으로 그리려면
 * 뒤집어서(reverse) 이어붙여야 한다(각 페이지 내부는 이미 오름차순으로 온다).
 */
export function useChatHistory(workspaceCode: string | null, folderId: number | null, videoId: number | null) {
  return useInfiniteQuery({
    queryKey: ["chat", "history", workspaceCode, folderId, videoId],
    queryFn: ({ pageParam }) =>
      fetchFolderChatHistory(folderId as number, { limit: PAGE_SIZE, beforeId: pageParam, videoId }),
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.next_cursor : undefined),
    enabled: workspaceCode !== null && folderId !== null,
  });
}
