// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ErrorNotice } from "@/components/error-notice";
import { ApiError } from "@/lib/api-client";

afterEach(cleanup);

describe("ErrorNotice", () => {
  it("오류 메시지와 requestId를 사용자에게 보여 준다", () => {
    const error = new ApiError({
      status: 500,
      message: "서버 오류",
      requestId: "req-abc",
    });
    render(<ErrorNotice error={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent("서버 오류");
    expect(screen.getByRole("alert")).toHaveTextContent("req-abc");
  });

  it("requestId가 없는 일반 오류는 메시지만 보여 준다", () => {
    render(<ErrorNotice error={new Error("알 수 없는 오류")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("알 수 없는 오류");
    expect(screen.queryByText(/요청 ID/)).toBeNull();
  });
});
