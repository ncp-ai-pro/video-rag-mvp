import { API_BASE } from "@/lib/config";

export class ApiError extends Error {
  // erasableSyntaxOnly가 켜져 있어 constructor 파라미터 프로퍼티는 쓸 수 없다.
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI는 오류를 {detail: string} 또는 {detail: ValidationError[]}로 준다. */
export async function readErrorMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg).join(", ");
  }
  return `요청에 실패했습니다. (HTTP ${response.status})`;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  // 204 No Content는 본문이 없다.
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
