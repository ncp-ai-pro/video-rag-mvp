import { CHAT_BASE, CHAT_CREDENTIALS } from "./config";
import { ApiError } from "./api";
import type { ChatHistoryPage, ChatResponse, Evidence } from "./types";

/**
 * 작업공간의 저장된 대화 기록을 불러온다. Chat 서버가 세션 쿠키로 작업공간을 식별한다.
 * assistant 메시지는 저장된 근거(evidence)를 함께 포함할 수 있다.
 */
export async function fetchChatHistory(options: { limit?: number; beforeId?: number | null } = {}): Promise<ChatHistoryPage> {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.beforeId) params.set("before_id", String(options.beforeId));
  const response = await fetch(`${CHAT_BASE}/chat/history?${params.toString()}`, {
    credentials: CHAT_CREDENTIALS,
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    throw new ApiError("대화 기록을 불러오지 못했습니다.", response.status);
  }
  const body = (await response.json()) as Partial<ChatHistoryPage>;
  const items = body.items ?? body.messages ?? [];
  return {
    items,
    messages: items,
    has_more: Boolean(body.has_more),
    next_cursor: body.next_cursor ?? null,
  };
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

export async function streamChat(
  query: string,
  onEvent: (event: ChatStreamEvent) => void,
  options: { limit?: number; signal?: AbortSignal; videoId?: number | null } = {},
): Promise<void> {
  // video_id를 보내면 백엔드가 그 영상으로 근거를 좁힌다. null이면 작업공간 전체.
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
    }),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.detail === "string"
        ? body.detail
        : "질문 요청에 실패했습니다.",
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

/** 스트리밍이 필요 없는 경우의 완료형 호출. */
export async function askChat(query: string, limit = 3): Promise<ChatResponse> {
  const response = await fetch(`${CHAT_BASE}/chat`, {
    method: "POST",
    credentials: CHAT_CREDENTIALS,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      typeof body?.detail === "string"
        ? body.detail
        : "질문 요청에 실패했습니다.",
      response.status,
    );
  }
  return (await response.json()) as ChatResponse;
}
