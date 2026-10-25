import { create } from "zustand";

export interface UiError {
  message: string;
  requestId?: string;
}

interface UiState {
  lastError: UiError | null;
  setLastError: (error: UiError) => void;
  clearLastError: () => void;
}

// 전역 UI 상태의 기본 스토어. 검수 화면 등 도메인 스토어는 stores/ 아래에 따로 추가한다
export const useUiStore = create<UiState>()((set) => ({
  lastError: null,
  setLastError: (error) => set({ lastError: error }),
  clearLastError: () => set({ lastError: null }),
}));
