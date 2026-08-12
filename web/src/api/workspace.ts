import { post, request } from "./client";
import type { Workspace } from "./types";

//작업공간 조회
export async function fetchMe() {
  return request<Workspace>("/auth/me");
}

//작업공간 코드로 연결
export async function connectWorkspace(workspaceCode: string) {
  return post<Workspace>("/auth/workspace", { workspace_code: workspaceCode });
}

//새 작업공간 생성
export async function createWorkspace() {
  return post<Workspace>("/auth/new-workspace");
}
