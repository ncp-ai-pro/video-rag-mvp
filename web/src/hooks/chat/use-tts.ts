import { useEffect, useRef, useState } from "react";

import { synthesizeSpeech } from "@/api/chat";
import type { TtsVoice } from "@/api/types";

/**
 * 답변 하나씩만 재생한다. 새로 재생하면 이전 오디오 URL은 즉시 해제한다.
 */
export function useTts(onError: (message: string) => void) {
  const [turnId, setTurnId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [voice, setVoice] = useState<TtsVoice>("nyounghwa");
  const urlRef = useRef<string | null>(null);

  const stop = () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
    setAudioUrl(null);
    setTurnId(null);
  };

  // 언마운트 시(영상 전환 등) 만들어 둔 blob URL을 정리한다.
  useEffect(() => () => stop(), []);

  const play = async (id: string, text: string) => {
    if (loading || !text.trim()) return;
    stop();
    setTurnId(id);
    setLoading(true);
    try {
      const blob = await synthesizeSpeech(text, voice);
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      setAudioUrl(url);
    } catch (error) {
      setTurnId(null);
      onError(error instanceof Error ? error.message : "음성 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return { turnId, loading, audioUrl, voice, setVoice, play, stop };
}
