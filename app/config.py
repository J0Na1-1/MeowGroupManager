from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bot_token: SecretStr = Field(validation_alias="TELEGRAM_BOT_TOKEN")
    database_url: str = "postgresql+asyncpg://bot:change-me@postgres:5432/tg_guard"
    token_secret: SecretStr
    fernet_key: SecretStr = Field(validation_alias="CONFIG_ENCRYPTION_KEY")
    admin_user_ids: str = ""
    cleanup_dry_run: bool = Field(True, validation_alias="DRY_RUN")
    group_id: int = 0

    @property
    def admins(self) -> frozenset[int]:
        return frozenset(int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip())
