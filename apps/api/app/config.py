"""환경변수 기반 앱 설정."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # 쉼표로 구분한 허용 출처 (예: "http://localhost:3000,https://app.example.com")
    cors_origins: str = "http://localhost:3000"
    # IP당 분당 허용 요청 수. 0 이하면 레이트 리밋을 끈다
    rate_limit_per_minute: int = 120
    # 비어 있으면 해당 연결 체크는 skipped 처리한다
    database_url: str | None = None
    redis_url: str | None = None
    log_level: str = "INFO"
    # true면 JSON 로그, false면 사람이 읽기 쉬운 콘솔 로그
    log_json: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
