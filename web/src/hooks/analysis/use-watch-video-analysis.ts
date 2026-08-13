import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAnalysisEvents } from "./use-analysis-events";
import type { AnalysisEvent, FolderVideo } from "@/api/types";

/**
 * 분석 중인 영상의 SSE 진행 상태를 folder-videos 쿼리 캐시에 직접 반영한다.
 * 화면은 useFolderVideos(folderId)만 구독하면 되고, 재조회 없이 자동으로 갱신된다.
 */
export function useWatchVideoAnalysis(folderId: number | null, videoId: number | null) {
  const queryClient = useQueryClient();

  const onEvent = useCallback(
    (event: AnalysisEvent) => {
      queryClient.setQueryData<FolderVideo[]>(["folder-videos", folderId], (current) =>
        current?.map((video) =>
          video.id === event.video_id
            ? {
                ...video,
                analysis_status: event.status,
                analysis_stage: event.progress.stage,
                analysis_message: event.progress.message,
                analysis_error: event.error,
                analysis_updated_at: event.updated_at,
              }
            : video,
        ),
      );
    },
    [queryClient, folderId],
  );

  useAnalysisEvents(videoId, onEvent);
}
