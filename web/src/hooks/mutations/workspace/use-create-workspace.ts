import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createWorkspace } from "@/api/workspace";
import type { UseMutationCallback } from "@/hooks/types";

export function useCreateWorkspace(callbacks?: UseMutationCallback) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createWorkspace,
    onSuccess: (workspace) => {
      queryClient.setQueryData(["workspace", "me"], workspace);
      queryClient.removeQueries({ queryKey: ["channels"] });
      queryClient.removeQueries({ queryKey: ["videos"] });
      queryClient.removeQueries({ queryKey: ["chat", "history"] });
      callbacks?.onSuccess?.();
    },
    onError: (error) => callbacks?.onError?.(error),
  });
}
