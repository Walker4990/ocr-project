import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "@/stores/ui-store";

describe("useUiStore", () => {
  beforeEach(() => useUiStore.setState(useUiStore.getInitialState()));

  it("마지막 오류를 저장하고 지운다", () => {
    useUiStore.getState().setLastError({ message: "실패", requestId: "r-1" });
    expect(useUiStore.getState().lastError?.requestId).toBe("r-1");
    useUiStore.getState().clearLastError();
    expect(useUiStore.getState().lastError).toBeNull();
  });
});
