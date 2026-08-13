import { useEffect, useRef, useState } from "react";

import { streamFolderChat } from "@/api/chat";
import { useChatHistory } from "@/hooks/queries/chat/use-chat-history";
import type { ChatMessage, Evidence, EvidenceMode } from "@/api/types";

/**
 * 한 번의 질문·답변·근거. 대화는 백엔드(GET /chat/history)에 작업공간별로 저장된다.
 * assistant 메시지에는 저장된 근거(evidence)가 함께 돌아오므로, 새로고침 후에도 다시 렌더링할 수 있다.
 */
export interface ChatTurn {
  id: string;
  question: string;
  answer: string;
  evidence: Evidence[];
  status: "streaming" | "done" | "error";
}

/** 서버의 평면 메시지 배열([user, assistant, ...])을 질문·답변 turn으로 묶는다. */
function messagesToTurns(messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let pendingQuestion: string | null = null;
  let pendingId: number | null = null;
  const push = (question: string, answer: string, evidence: Evidence[] = []) =>
    turns.push({
      id: pendingId !== null ? `message-${pendingId}` : crypto.randomUUID(),
      question,
      answer,
      evidence,
      status: "done",
    });

  for (const message of messages) {
    if (message.role === "user") {
      if (pendingQuestion !== null) push(pendingQuestion, "");
      pendingQuestion = message.content;
      pendingId = message.id;
    } else {
      push(pendingQuestion ?? "", message.content, message.evidence ?? []);
      pendingQuestion = null;
      pendingId = null;
    }
  }
  if (pendingQuestion !== null) push(pendingQuestion, "");
  return turns;
}

/**
 * 대화 화면(질문 입력, 스트리밍 답변, 근거, 과거 대화 페이지네이션)의 상태와 동작을
 * 전부 감당하는 훅. 화면 컴포넌트는 이 훅이 주는 값을 그리고, 스크롤 위치 같은
 * DOM 세부사항만 직접 처리한다.
 */
export function useChat(
  workspaceCode: string | null,
  folderId: number | null,
  videoId: number | null,
  onError: (message: string) => void,
) {
  // 대화는 폴더 단위로 저장·조회된다. videoId가 있으면 그 영상으로, 없으면 폴더 전체로 좁힌다.
  const history = useChatHistory(workspaceCode, folderId, videoId);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [query, setQuery] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [evidenceMode, setEvidenceMode] = useState<EvidenceMode>("simple");
  const abortRef = useRef<AbortController | null>(null);

  // 폴더나 영상이 바뀌면 진행 중이던 스트리밍을 끊는다. 폴더 미선택 상태면 대화도 비운다.
  useEffect(() => {
    abortRef.current?.abort();
    setStreaming(false);
    if (folderId === null) setTurns([]);
  }, [folderId, videoId]);

  // 페이지들은 최신이 먼저 오므로 뒤집어서 오래된→최신 순으로 합친다.
  useEffect(() => {
    if (!history.data) return;
    const messages = [...history.data.pages].reverse().flatMap((page) => page.items);
    setTurns(messagesToTurns(messages));
  }, [history.data]);

  const loadOlderHistory = () => {
    if (history.hasNextPage && !history.isFetchingNextPage) {
      void history.fetchNextPage();
    }
  };

  const ask = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || streaming || folderId === null) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const id = crypto.randomUUID();
    setQuery("");
    setStreaming(true);
    setTurns((prev) => [...prev, { id, question: trimmed, answer: "", evidence: [], status: "streaming" }]);

    const patch = (fn: (turn: ChatTurn) => ChatTurn) =>
      setTurns((prev) => prev.map((turn) => (turn.id === id ? fn(turn) : turn)));

    try {
      await streamFolderChat(
        folderId,
        trimmed,
        (event) => {
          switch (event.type) {
            case "evidence":
              patch((turn) => ({ ...turn, evidence: event.evidence }));
              break;
            case "token":
              patch((turn) => ({ ...turn, answer: turn.answer + event.text }));
              break;
            case "done":
              patch((turn) => ({ ...turn, evidence: event.evidence }));
              break;
            case "error":
              onError(event.message);
              patch((turn) => ({ ...turn, status: "error" }));
              break;
          }
        },
        { evidenceMode, signal: controller.signal, videoId },
      );
      patch((turn) => (turn.status === "streaming" ? { ...turn, status: "done" } : turn));
    } catch (error) {
      if (controller.signal.aborted) return;
      onError(error instanceof Error ? error.message : "질문 요청에 실패했습니다.");
      patch((turn) => ({ ...turn, status: "error" }));
    } finally {
      setStreaming(false);
    }
  };

  return {
    turns,
    query,
    setQuery,
    streaming,
    ask,
    /** 폴더만 선택하면 질문할 수 있다(영상 미선택 시 폴더 전체를 검색한다). */
    canAsk: folderId !== null,
    evidenceMode,
    setEvidenceMode,
    historyHasMore: history.hasNextPage ?? false,
    historyLoading: history.isFetchingNextPage,
    loadOlderHistory,
  };
}

/** ChatPanel·EvidencePanel이 함께 쓰는, useChat이 반환하는 상태·동작의 타입. */
export type UseChatResult = ReturnType<typeof useChat>;
