from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
from datetime import datetime, timezone

import asyncssh
from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.db.models import AdminConfig, GroupMember, Verification
from app.services.config_crypto import EncryptedConfig
from app.services.security import TokenService


def build_start_link(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start={token}"


class BindingStates(StatesGroup):
    username = State()
    command = State()
    waiting_confirmation = State()


def register(token_service: TokenService, session_factory, bot: Bot, encryption_key: str) -> Router:
    local = Router(name="verification")
    crypto = EncryptedConfig(encryption_key.encode())

    async def config_data() -> dict[str, str]:
        async with session_factory() as session:
            row = await session.scalar(select(AdminConfig).order_by(AdminConfig.id).limit(1))
        if row is None:
            raise RuntimeError("未配置妙妙屋 X SSH")
        return json.loads(crypto.decrypt(row.encrypted_payload))

    async def run_readonly_sql(sql: str) -> str:
        data = await config_data()
        host = data["ssh_host"]
        ssh_user = data["ssh_user"]
        password = data["ssh_password"]
        port = int(data.get("ssh_port", 22))
        if data.get("deployment") == "docker":
            command = (
                "container=$(docker ps --format '{{.Names}} {{.Image}}' | "
                "awk 'tolower($1) ~ /miaomiaowux/ && tolower($2) ~ /postgres/ {print $1; exit}'); "
                "test -n \"$container\" && docker exec \"$container\" "
                "psql -U mmwx -d mmwx -Atc " + shlex.quote(sql)
            )
        else:
            command = (
                f"PGPASSWORD={shlex.quote(data.get('db_password', ''))} psql -h 127.0.0.1 "
                f"-p {shlex.quote(data.get('db_port', '5432'))} "
                f"-U {shlex.quote(data.get('db_user', 'mmwx'))} "
                f"-d {shlex.quote(data.get('db_name', 'mmwx'))} -Atc {shlex.quote(sql)}"
            )
        try:
            async with asyncssh.connect(host, port=port, username=ssh_user, password=password, known_hosts=None, login_timeout=15) as connection:
                result = await asyncio.wait_for(connection.run(command, check=False), timeout=20)
        except Exception as exc:
            raise RuntimeError(f"主控查询失败：{type(exc).__name__}") from exc
        if result.exit_status != 0:
            raise RuntimeError("主控数据库查询失败")
        return (result.stdout or "").strip()

    async def binding_settings() -> tuple[str, str]:
        async with session_factory() as session:
            row = await session.scalar(select(AdminConfig).order_by(AdminConfig.id).limit(1))
        if row is None:
            return "https://localhost", "JonahMeow_bot"
        data = json.loads(crypto.decrypt(row.encrypted_payload))
        host = data.get("ssh_host", "localhost")
        login_url = data.get("binding_login_url") or (host if host.startswith(("http://", "https://")) else f"https://{host}")
        return login_url, data.get("binding_bot_username", "JonahMeow_bot")
    async def binding_confirmed(username: str, telegram_id: int) -> bool:
        sql = (
            "SELECT 1 FROM public.users "
            f"WHERE lower(username)=lower({shlex.quote(username)}) "
            f"AND telegram_id={int(telegram_id)} LIMIT 1;"
        )
        return await run_readonly_sql(sql) == "1"

    @local.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        payload = (message.text or "").split(maxsplit=1)
        token = payload[1] if len(payload) == 2 else ""
        user_id = message.from_user.id if message.from_user else 0
        if not token:
            if message.chat.type == "private":
                await state.set_state(BindingStates.username)
                await state.update_data(chat_id=None)
                await message.answer("请发送你的妙妙屋 X 用户名。")
            else:
                await message.answer("请点击群内新人验证按钮进入绑定流程。")
            return
        if not token_service.validate(token, user_id):
            await message.answer("验证链接无效、已过期或已使用，请重新获取。")
            return
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with session_factory() as session:
            verification = await session.scalar(select(Verification).where(Verification.token_hash == digest))
            if verification is None:
                await message.answer("验证链接无效、已过期或已使用，请重新获取。"); return
            expires_at = verification.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if verification.used or expires_at <= datetime.now(timezone.utc):
                await message.answer("验证链接无效、已过期或已使用，请重新获取。"); return
            chat_id = verification.chat_id
        await state.set_state(BindingStates.username)
        await state.update_data(chat_id=chat_id)
        await message.answer("请发送你的妙妙屋 X 用户名。")

    @local.message(F.text == "点击绑定 TG")
    async def binding_start(message: Message, state: FSMContext) -> None:
        if message.chat.type == "private":
            await state.set_state(BindingStates.username)
            await message.answer("请发送你的妙妙屋 X 用户名。")

    @local.message(BindingStates.username)
    async def binding_username(message: Message, state: FSMContext) -> None:
        username = (message.text or "").strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", username):
            await message.answer("用户名格式不正确，请重新发送。")
            return
        await state.update_data(username=username)
        await state.set_state(BindingStates.command)
        login_url, bot_username = await binding_settings()
        await message.answer(
            f"请打开妙妙屋 X 登录页面：\n{login_url}\n\n"
            "点击右上角头像，选择“生成绑定码”，复制生成的 `/start XXXXX` 命令并发送给我。\n"
            f"完成后将跳转到官方机器人 @{bot_username}。"
        )

    @local.message(BindingStates.command)
    async def binding_command(message: Message, state: FSMContext) -> None:
        match = re.fullmatch(r"\s*/start(?:\s+|=)([A-Za-z0-9_-]{6,128})\s*", message.text or "")
        if not match:
            await message.answer("格式不正确，请发送类似 `/start 436EFD726202` 的绑定命令。")
            return
        data = await state.get_data()
        code = match.group(1)
        _, bot_username = await binding_settings()
        await state.update_data(code=code)
        await state.set_state(BindingStates.waiting_confirmation)
        await message.answer(
            "已收到绑定命令，点击下面按钮打开官方机器人完成绑定：",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="点击此绑定 TG", url=f"https://t.me/{bot_username}?start={code}")]])
        )
        await message.answer("完成后返回这里发送：我已完成绑定")

    @local.message(BindingStates.waiting_confirmation, F.text == "我已完成绑定")
    async def binding_check(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        username = data.get("username")
        chat_id = data.get("chat_id")
        if not username:
            await message.answer("绑定流程已过期，请重新开始绑定。")
            await state.clear()
            return
        try:
            confirmed = await binding_confirmed(username, message.from_user.id)
        except RuntimeError as exc:
            await message.answer(f"{exc}，暂不解除群组限制。")
            return
        if not confirmed:
            await message.answer("主控尚未确认当前 Telegram 账号绑定，请先完成官方机器人绑定。")
            return
        if not chat_id:
            await message.answer("绑定已确认；当前没有关联的待验证群组。")
            await state.clear()
            return
        async with session_factory() as session:
            verification = await session.scalar(select(Verification).where(Verification.chat_id == chat_id, Verification.telegram_user_id == message.from_user.id, Verification.used.is_(False)))
            if verification is None:
                await message.answer("验证记录已过期，请重新加入群组。"); await state.clear(); return
            verification.used = True
            member = await session.scalar(select(GroupMember).where(GroupMember.chat_id == chat_id, GroupMember.telegram_user_id == message.from_user.id))
            if member:
                member.verified_at = datetime.utcnow()
            await session.commit()
        try:
            await bot.restrict_chat_member(chat_id, message.from_user.id, permissions=ChatPermissions(can_send_messages=True, can_send_other_messages=True, can_add_web_page_previews=True))
        except Exception:
            await message.answer("已确认绑定，但解除群组限制失败，请联系管理员。")
            return
        await state.clear()
        await message.answer("绑定成功，已解除群组禁言。")

    return local
