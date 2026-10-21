// 개발 환경 스모크 테스트: 고정한 프레임워크 메이저 버전을 확인한다.
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

describe("개발 환경", () => {
  it("React 19를 사용한다", () => {
    expect(require("react/package.json").version).toMatch(/^19\./);
  });

  it("Next.js 15를 사용한다", () => {
    expect(require("next/package.json").version).toMatch(/^15\./);
  });
});