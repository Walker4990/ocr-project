import { ApiError } from "@/lib/api-client";

// 오류를 삼키지 않고 보여 준다. API 오류는 문의·추적용 requestId를 함께 표시한다
export function ErrorNotice({ error }: { error: Error }) {
  const requestId = error instanceof ApiError ? error.requestId : undefined;
  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <p>{error.message}</p>
      {requestId && (
        <p className="mt-1 font-mono text-xs">요청 ID: {requestId}</p>
      )}
    </div>
  );
}
