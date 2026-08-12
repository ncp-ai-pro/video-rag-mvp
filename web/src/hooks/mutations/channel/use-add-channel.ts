import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createChannel, scanChannel } from "@/api/channel";
import type { Channel } from "@/api/types";
import type { UseMutationCallback } from "@/hooks/types";

/** 채널을 등록하고 곧바로 첫 영상 탐색까지 등록한다(홈·사이드바가 공유하는 동작). */
export function useAddChannel(callbacks?: UseMutationCallback & { onSettled?: (channel: Channel) => void }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (url: string) => {
      const channel = await createChannel(url);
      await scanChannel(channel.id);
      return channel;
    },
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: ["channels"] });
      callbacks?.onSuccess?.();
      callbacks?.onSettled?.(channel);
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
