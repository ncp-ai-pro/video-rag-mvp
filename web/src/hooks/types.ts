/** mutation 훅들이 공통으로 받는 성공·실패 콜백. */
export interface UseMutationCallback {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}
