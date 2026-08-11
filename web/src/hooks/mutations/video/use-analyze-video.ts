import { useMutation, useQueryClient } from "@tanstack/react-query";

import { analyzeVideo } from "@/api/video";
import type { AnalysisEvent, Video } from "@/api/types";
import type { UseMutationCallback } from "@/hooks/types";

/** 분석 작업 등록 성공 시, SSE 첫 이벤트를 기다리지 않고 목록 캐시를 즉시 queued로 낙관 갱신한다. */
export function useAnalyzeVideo(channelId: number | null, callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: analyzeVideo,
    onSuccess: (job, videoId) => {
      const event: AnalysisEvent = {
        video_id: videoId,
        job_id: job.job_id,
        status: "queued",
        progress: { stage: "queued", message: "분석 작업을 기다리고 있습니다." },
        error: null,
        updated_at: null,
      };
      queryClient.setQueryData<Video[]>(["videos", channelId], (current) =>
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
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
