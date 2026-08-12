import { useState } from "react";

import { exportChatTranscript } from "@/api/chat";

export function useExportChat(onError: (message: string) => void) {
  const [exportingFormat, setExportingFormat] = useState<"txt" | "pdf" | null>(null);

  const exportChat = async (
    videoId: number | null | undefined,
    messageIds: number[] | undefined,
    format: "txt" | "pdf",
  ) => {
    if (exportingFormat) return;
    setExportingFormat(format);
    try {
      const blob = await exportChatTranscript(videoId, messageIds, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const base = videoId != null ? `chat-export-video-${videoId}` : "chat-export";
      link.download = `${base}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      onError(error instanceof Error ? error.message : "대화 내보내기에 실패했습니다.");
    } finally {
      setExportingFormat(null);
    }
  };

  return { exportingFormat, exportChat };
}