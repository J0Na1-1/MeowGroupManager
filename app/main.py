from __future__ import annotations

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllChatAdministrators
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import Settings
from app.handlers.admin import register as register_admin
from app.handlers.verification import register as register_verification
from app.services.security import TokenService


async def main() -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async def consume(_token: str, _user_id: int) -> bool:
        # Production implementation must atomically mark the token used in SQL.
        return True
    async def status() -> str:
        async with sessions():
            return "数据库连接可用"
    bot = Bot(settings.bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.include_router(register_admin(
        bot,
        settings.admins,
        status,
        sessions,
        settings.fernet_key.get_secret_value(),
        TokenService(settings.token_secret.get_secret_value()),
    ))
    dispatcher.include_router(register_verification(
        TokenService(settings.token_secret.get_secret_value()),
        sessions,
        bot,
        settings.fernet_key.get_secret_value(),
    ))
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="启动机器人"),
            BotCommand(command="admin", description="打开管理员面板"),
            BotCommand(command="task", description="打开任务面板"),
            BotCommand(command="cancel", description="取消当前操作"),
        ],
        scope=BotCommandScopeAllChatAdministrators(),
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
