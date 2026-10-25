import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, createRequestId } from "@/lib/api-client";

function mockFetch(response: Response) {
  const fn = vi.fn<typeof fetch>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

function sentHeaders(fn: ReturnType<typeof mockFetch>): Headers {
  const init = fn.mock.calls[0][1];
  return new Headers(init?.headers);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("createRequestId", () => {
  it("호출마다 다른 값을 만든다", () => {
    expect(createRequestId()).not.toBe(createRequestId());
  });
});

describe("apiFetch", () => {
  it("요청에 X-Request-ID 헤더를 실어 보낸다", async () => {
    const fn = mockFetch(Response.json({ ok: true }));
    await apiFetch("/health");
    expect(sentHeaders(fn).get("X-Request-ID")).toMatch(/\S+/);
  });

  it("호출자가 requestId를 주면 그 값을 쓴다", async () => {
    const fn = mockFetch(Response.json({ ok: true }));
    await apiFetch("/health", { requestId: "req-123" });
    expect(sentHeaders(fn).get("X-Request-ID")).toBe("req-123");
  });

  it("NEXT_PUBLIC_API_URL을 기준 주소로 쓴다", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test:9000/");
    const fn = mockFetch(Response.json({}));
    await apiFetch("/health");
    expect(fn.mock.calls[0][0]).toBe("http://api.test:9000/health");
  });

  it("성공 응답은 JSON으로 파싱해 돌려준다", async () => {
    mockFetch(Response.json({ status: "ok" }));
    await expect(apiFetch<{ status: string }>("/health")).resolves.toEqual({
      status: "ok",
    });
  });

  it("본문이 없는 204는 undefined를 돌려준다", async () => {
    mockFetch(new Response(null, { status: 204 }));
    await expect(apiFetch("/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("JSON 본문은 Content-Type을 지정한다", async () => {
    const fn = mockFetch(Response.json({}));
    await apiFetch("/x", { method: "POST", json: { a: 1 } });
    expect(sentHeaders(fn).get("Content-Type")).toBe("application/json");
    expect(fn.mock.calls[0][1]?.body).toBe('{"a":1}');
  });

  it("오류 응답은 본문의 requestId를 담은 ApiError를 던진다", async () => {
    mockFetch(
      Response.json(
        {
          error: {
            code: "invalid_file",
            message: "지원하지 않는 형식",
            requestId: "srv-1",
          },
        },
        { status: 422 },
      ),
    );
    const error = await apiFetch("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.code).toBe("invalid_file");
    expect(apiError.message).toBe("지원하지 않는 형식");
    expect(apiError.requestId).toBe("srv-1");
  });

  it("본문에 requestId가 없으면 응답 헤더를 쓴다", async () => {
    mockFetch(
      new Response("boom", { status: 500, headers: { "X-Request-ID": "hdr-1" } }),
    );
    const error = (await apiFetch("/x").catch((e: unknown) => e)) as ApiError;
    expect(error.requestId).toBe("hdr-1");
    expect(error.status).toBe(500);
  });

  it("서버가 requestId를 주지 않으면 보낸 값을 담는다", async () => {
    mockFetch(new Response("boom", { status: 500 }));
    const error = (await apiFetch("/x", { requestId: "mine" }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(error.requestId).toBe("mine");
  });

  it("네트워크 오류도 보낸 requestId를 담은 ApiError로 던진다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    const error = (await apiFetch("/x", { requestId: "net-1" }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.requestId).toBe("net-1");
  });
});
