import { useEffect } from "react";

import { API_BASE } from "@/lib/config";
import type { AnalysisEvent } from "@/api/types";

/**
 * GET /videos/{id}/events 를 구독한다.
 *
 * 이 endpoint는 GET이라 EventSource를 그대로 쓸 수 있고,
 * 서버가 `retry: 3000`을 보내므로 끊겨도 브라우저가 알아서 재연결한다.
 * 서버는 succeeded/failed를 보낸 뒤 stream을 닫으므로 그때 구독을 정리한다.
 */
export function useAnalysisEvents(
  videoId: number | null,
  onEvent: (event: AnalysisEvent) => void,
) {
  useEffect(() => {
    if (videoId === null) return;

    const source = new EventSource(`${API_BASE}/videos/${videoId}/events`, {
      withCredentials: true,
    });

    source.addEventListener("analysis_status", (event) => {
      let payload: AnalysisEvent;
      try {
        payload = JSON.parse((event as MessageEvent<string>).data);
      } catch {
        return;
      }
      onEvent(payload);
      // terminal 상태 이후에는 서버가 stream을 닫는다. 재연결을 막기 위해 즉시 close.
      if (payload.status === "succeeded" || payload.status === "failed") {
        source.close();
      }
    });

    return () => source.close();
    // onEvent는 호출부(use-watch-video-analysis)에서 안정된 참조로 넘긴다.
  }, [videoId, onEvent]);
}
