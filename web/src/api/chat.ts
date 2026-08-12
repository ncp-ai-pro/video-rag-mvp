import { ApiError } from "./client";
import { CHAT_BASE, CHAT_CREDENTIALS } from "@/lib/config";
import type { ChatHistoryPage, ChatResponse, Evidence, EvidenceMode } from "./types";

/**
 * 작업공간의 저장된 대화 기록을 최신순 커서로 페이지네이션해서 불러온다.
 * videoId를 주면 그 영상의 대화만 좁혀서 가져온다(히스토리도 영상 단위로 저장된다).
 * Chat 서버가 세션 쿠키로 작업공간을 식별한다. assistant 메시지는 그때 근거도 함께 저장돼 있다.
 */
export async function fetchChatHistory(
  options: { limit?: number; beforeId?: number | null; videoId?: number | null } = {},
): Promise<ChatHistoryPage> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.beforeId != null) params.set("before_id", String(options.beforeId));
  if (options.videoId != null) params.set("video_id", String(options.videoId));

  const response = await fetch(`${CHAT_BASE}/chat/history?${params}`, {
    credentials: CHAT_CREDENTIALS,
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    throw new ApiError("대화 기록을 불러오지 못했습니다.", response.status);
  }
  return (await response.json()) as ChatHistoryPage;
}

/**
 * /chat/stream은 SSE지만 POST라서 EventSource를 쓸 수 없다.
 * fetch의 ReadableStream을 직접 읽어 프레임을 파싱한다.
 */

export type ChatStreamEvent =
  | { type: "evidence"; evidence: Evidence[] }
  | { type: "token"; text: string }
  | { type: "done"; evidence: Evidence[] }
  | { type: "error"; message: string };

/** SSE 한 프레임(빈 줄로 구분된 블록)을 event/data로 분해한다. */
function parseFrame(frame: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    // ':'로 시작하는 줄은 heartbeat 같은 주석이라 무시한다.
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  return dataLines.length > 0 ? { event, data: dataLines.join("\n") } : null;
}

function toStreamEvent(event: string, raw: string): ChatStreamEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  const payload = data as {
    evidence?: Evidence[];
    text?: string;
    message?: string;
  };
  switch (event) {
    case "evidence":
      return { type: "evidence", evidence: payload.evidence ?? [] };
    case "token":
      return { type: "token", text: payload.text ?? "" };
    case "done":
      return { type: "done", evidence: payload.evidence ?? [] };
    case "error":
      return {
        type: "error",
        message: payload.message ?? "Chat 응답 생성에 실패했습니다.",
      };
    default:
      return null;
  }
}

/**
 * video_id를 보내면 백엔드가 그 영상으로 근거를 좁힌다. null이면 작업공간 전체.
 * evidenceMode="precise"|"ultra"면 각 근거에 질문과 겹치는 문장(highlight)이 함께 붙어 온다.
 */
export async function streamChat(
  query: string,
  onEvent: (event: ChatStreamEvent) => void,
  options: {
    limit?: number;
    signal?: AbortSignal;
    videoId?: number | null;
    evidenceMode?: EvidenceMode;
  } = {},
): Promise<void> {
  const response = await fetch(`${CHAT_BASE}/chat/stream`, {
    method: "POST",
    credentials: CHAT_CREDENTIALS,
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      query,
      limit: options.limit ?? 3,
      video_id: options.videoId ?? null,
      evidence_mode: options.evidenceMode ?? "simple",
    }),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.detail === "string" ? body.detail : "질문 요청에 실패했습니다.",
      response.status,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (frame: string) => {
    const parsed = parseFrame(frame);
    if (!parsed) return;
    const streamEvent = toStreamEvent(parsed.event, parsed.data);
    if (streamEvent) onEvent(streamEvent);
  };

  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      flush(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) {
      // 마지막 프레임이 빈 줄 없이 끝났을 수 있다.
      if (buffer.trim()) flush(buffer);
      return;
    }
  }
}

/** 답변 텍스트를 CLOVA Voice로 합성해 mp3 오디오로 받는다. */
export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${CHAT_BASE}/tts`, {
    method: "POST",
    credentials: CHAT_CREDENTIALS,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.detail === "string" ? body.detail : "음성 생성에 실패했습니다.",
      response.status,
    );
  }
  return response.blob();
}

/** 스트리밍이 필요 없는 완료형 호출. */
export async function askChat(
  query: string,
  options: { limit?: number; evidenceMode?: EvidenceMode; videoId?: number | null } = {},
): Promise<ChatResponse> {
  const response = await fetch(`${CHAT_BASE}/chat`, {
    method: "POST",
    credentials: CHAT_CREDENTIALS,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      limit: options.limit ?? 3,
      video_id: options.videoId ?? null,
      evidence_mode: options.evidenceMode ?? "simple",
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.detail === "string" ? body.detail : "질문 요청에 실패했습니다.",
      response.status,
    );
  }
  return (await response.json()) as ChatResponse;
}

export async function exportChatTranscript(
  videoId?: number | null,
  messageIds?: number[],
  format: "txt" | "pdf" = "txt",
): Promise<Blob> {
  const params = new URLSearchParams();
  if (videoId != null) params.set("video_id", String(videoId));
  if (messageIds && messageIds.length > 0) {
    for (const id of messageIds) params.append("message_ids", String(id));
  }
  params.set("format", format);
  const response = await fetch(`${CHAT_BASE}/chat/export?${params.toString()}`, {
    credentials: CHAT_CREDENTIALS,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.detail === "string" ? body.detail : "대화 내보내기에 실패했습니다.",
      response.status,
    );
  }
  return response.blob();
}
