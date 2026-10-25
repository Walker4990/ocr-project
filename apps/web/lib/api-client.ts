// API 클라이언트: 모든 요청에 X-Request-ID를 싣고, 실패 시 requestId를 담은 ApiError를 던진다.
// 응답 타입은 백엔드 OpenAPI에서 생성한 타입을 호출부에서 제네릭으로 넘긴다 (any 금지).

const REQUEST_ID_HEADER = "X-Request-ID";
const DEFAULT_API_URL = "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly requestId: string;

  constructor(params: {
    status: number;
    message: string;
    requestId: string;
    code?: string;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.requestId = params.requestId;
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  /** 직접 지정하지 않으면 새로 만든다. */
  requestId?: string;
  /** JSON으로 직렬화해 본문에 싣는다. */
  json?: unknown;
  body?: BodyInit | null;
}

export function createRequestId(): string {
  return crypto.randomUUID();
}

function getBaseUrl(): string {
  // 호출 시점에 읽는다. 빌드 때 번들에 박힌 값(NEXT_PUBLIC_*)을 쓴다
  const url = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
  return url.replace(/\/+$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function pickString(source: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value !== "") return value;
  }
  return undefined;
}

async function toApiError(
  response: Response,
  sentRequestId: string,
): Promise<ApiError> {
  const text = await response.text().catch(() => "");
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    body = undefined;
  }
  const fields = isRecord(body) ? body : {};

  return new ApiError({
    status: response.status,
    code: pickString(fields, "code"),
    message:
      pickString(fields, "message", "detail") ??
      (text || `요청 실패 (HTTP ${response.status})`),
    // 우선순위: 응답 본문 > 응답 헤더 > 우리가 보낸 값
    requestId:
      pickString(fields, "requestId", "request_id") ??
      response.headers.get(REQUEST_ID_HEADER) ??
      sentRequestId,
  });
}

export async function apiFetch<T = void>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { requestId = createRequestId(), json, headers, body, ...init } = options;

  const finalHeaders = new Headers(headers);
  finalHeaders.set(REQUEST_ID_HEADER, requestId);
  if (json !== undefined) finalHeaders.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${getBaseUrl()}${path}`, {
      ...init,
      headers: finalHeaders,
      body: json !== undefined ? JSON.stringify(json) : body,
    });
  } catch (cause) {
    throw new ApiError({
      status: 0,
      code: "network_error",
      message:
        cause instanceof Error
          ? `서버에 연결하지 못했습니다: ${cause.message}`
          : "서버에 연결하지 못했습니다",
      requestId,
    });
  }

  if (!response.ok) throw await toApiError(response, requestId);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
