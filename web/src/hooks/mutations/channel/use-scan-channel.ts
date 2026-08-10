import { useMutation } from "@tanstack/react-query";

import { scanChannel } from "@/api/channel";
import type { UseMutationCallback } from "@/hooks/types";

/** 이미 등록된 채널에서 새 영상 탐색 작업만 다시 등록한다. */
export function useScanChannel(callbacks?: UseMutationCallback) {
  return useMutation({
    mutationFn: scanChannel,
    onSuccess: () => callbacks?.onSuccess?.(),
    onError: (error) => callbacks?.onError?.(error),
  });
}
