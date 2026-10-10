from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import asyncio
import hashlib
import logging
import json
import re

logger = logging.getLogger("tg_guard.member")
from aiogram import Bot, F, Router
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AdminConfig, GroupMember, ManagedGroup, Verification
from app.services.security import TokenService
from app.services.config_crypto import EncryptedConfig
from app.handlers.verification import build_start_link
from app.services.discovery import DiscoveryError, discover_database, discover_user_table
from app.services.mmwx_query import query_mmwx_users
from app.services.tasks import TaskController

PanelStatus = Callable[[], Awaitable[str]]
MENU = {"添加当前群组", "我的群组", "被移除的用户", "群组设置", "用户 TG 绑定", "妙妙屋 X 配置", "清理任务", "任务", "运行模式", "审核记录", "系统状态", "帮助"}
TASK_MENU = {"开启任务", "暂停任务", "立即执行清理", "查看查询报告", "任务设置", "返回主面板"}
MODE_MENU = {"仅报告（dry-run）", "仅查询不处理", "自动移出成员", "返回主面板"}
MMWX_MENU = {"主控地址", "部署方式", "SSH 端口", "SSH 只读用户", "SSH 密码", "数据库用户", "数据库密码", "Meow_bot", "查看当前配置", "开始连接配置", "重新配置连接", "返回主面板"}
GROUP_MENU = {"开启新人验证", "关闭新人验证", "开启白名单", "关闭白名单", "验证机器人权限", "返回主面板"}

class TgBindingSettings(StatesGroup):
    login_url = State()
    bot_username = State()

class MMWXSettings(StatesGroup):
    field = State()

class Wizard(StatesGroup):
    ssh_host = State()
    deployment = State()
    ssh_port = State()
    ssh_user = State()
    ssh_password = State()
    db_user = State()
    db_password = State()
    table = State()


def panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="添加当前群组"), KeyboardButton(text="我的群组")],
        [KeyboardButton(text="被移除的用户"), KeyboardButton(text="群组设置")],
        [KeyboardButton(text="用户 TG 绑定"), KeyboardButton(text="妙妙屋 X 配置")],
        [KeyboardButton(text="清理任务"), KeyboardButton(text="任务")],
        [KeyboardButton(text="运行模式"), KeyboardButton(text="审核记录")],
        [KeyboardButton(text="系统状态"), KeyboardButton(text="帮助")]], resize_keyboard=True, is_persistent=True, input_field_placeholder="请选择管理功能")


def task_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="开启任务"), KeyboardButton(text="暂停任务")],
        [KeyboardButton(text="立即执行清理"), KeyboardButton(text="查看查询报告")],
        [KeyboardButton(text="任务设置"), KeyboardButton(text="返回主面板")]],
        resize_keyboard=True, is_persistent=True, input_field_placeholder="请选择任务操作")


def mode_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="仅报告（dry-run）"), KeyboardButton(text="仅查询不处理")], [KeyboardButton(text="自动移出成员")], [KeyboardButton(text="返回主面板")]], resize_keyboard=True)


def mmwx_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="主控地址"), KeyboardButton(text="部署方式")], [KeyboardButton(text="SSH 端口"), KeyboardButton(text="SSH 只读用户")], [KeyboardButton(text="SSH 密码"), KeyboardButton(text="数据库用户")], [KeyboardButton(text="数据库密码"), KeyboardButton(text="Meow_bot")], [KeyboardButton(text="查看当前配置")], [KeyboardButton(text="开始连接配置"), KeyboardButton(text="重新配置连接")], [KeyboardButton(text="返回主面板")]], resize_keyboard=True, is_persistent=True)


def group_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="开启新人验证"), KeyboardButton(text="关闭新人验证")], [KeyboardButton(text="开启白名单"), KeyboardButton(text="关闭白名单")], [KeyboardButton(text="验证机器人权限")], [KeyboardButton(text="返回主面板")]], resize_keyboard=True)


def mode_text(mode: str = "dry_run") -> str:
    labels = {"dry_run": "dry-run（仅报告，不移除）", "query_only": "仅查询（仅核对绑定状态）", "auto_remove": "自动移除（仅管理员明确开启后生效）"}
    return "运行模式\n\n当前模式：" + labels.get(mode, mode) + "\n\n选择后会应用到已添加群组。"


def group_text() -> str:
    return "群组设置\n\n新人验证：可开启/关闭\n白名单：可开启/关闭\n机器人权限：可验证\n\n请点击下方按钮。"


def removed_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="查看被移除用户")], [KeyboardButton(text="返回主面板")]], resize_keyboard=True)


def removed_text(rows: list[GroupMember]) -> str:
    if not rows:
        return "被移除的用户\n\n暂无记录。"
    return "被移除的用户\n\n" + "\n".join(f"@{row.username or '无用户名'} | Telegram ID：{row.telegram_user_id}\n移出时间：{row.removed_at}" for row in rows)


def task_text(mode: str = "dry_run", enabled: bool = False) -> str:
    labels = {"dry_run": "dry-run", "query_only": "仅查询", "auto_remove": "自动移除"}
    return ("任务面板\n\n查询任务：每日 09:00（Asia/Hong_Kong）\n"
            f"当前状态：{'已开启' if enabled else '已暂停'}\n运行模式：{labels.get(mode, mode)}\n"
            "报告会逐项显示群成员 Telegram ID 与妙妙屋 X telegram_id 匹配结果。")


def panel_text() -> str:
    return ("TG Group Guard 管理员面板\n\n请选择功能：\n"
            "• 添加当前群组：将当前群加入守护范围\n• 群组设置：新人验证、白名单和权限\n"
            "• 妙妙屋 X 配置：SSH、数据库和字段映射\n• 定时清理：每日 09:00 Asia/Hong_Kong\n"
            "• 审核记录：查看检查和操作审计\n\n默认 dry-run，不会自动移除成员。")


def auto_config(data: dict[str, str], db_type: str, table: str) -> dict[str, str]:
    return {**data, "db_type": db_type, "table": table, "ssh_port": "22", "db_path": "-",
            "db_host": data.get("ssh_host", "-"), "db_port": {"postgresql": "5432", "mysql": "3306", "sqlite": "-"}[db_type],
            "db_name": "mmwx", "db_user": "mmwx", "tg_username": "username", "tg_user_id": "telegram_user_id",
            "bind_status": "bind_status", "subscription_status": "subscription_status", "expires_at": "expires_at"}


def register(bot: Bot, admin_ids: frozenset[int], status_provider: PanelStatus, session_factory: Callable[[], AsyncSession], encryption_key: str, token_service: TokenService) -> Router:
    router = Router(name="admin")
    tasks = TaskController()
    crypto = EncryptedConfig(encryption_key.encode())
    def allowed(message: Message) -> bool: return bool(message.from_user and message.from_user.id in admin_ids)

    async def remove_if_unverified(group_id: int, user_id: int, expires_at: datetime) -> None:
        delay = max(0, (expires_at - datetime.now(timezone.utc)).total_seconds())
        await asyncio.sleep(delay)
        async with session_factory() as session:
            group = await session.scalar(select(ManagedGroup).where(ManagedGroup.chat_id == group_id))
            member = await session.scalar(select(GroupMember).where(GroupMember.chat_id == group_id, GroupMember.telegram_user_id == user_id))
            if group is None or group.cleanup_mode != "auto_remove" or member is None or member.verified_at is not None or member.removed_at is not None:
                return
            verification = await session.scalar(select(Verification).where(Verification.chat_id == group_id, Verification.telegram_user_id == user_id, Verification.used.is_(False)))
            if verification is not None:
                verification.used = True
            member.removed_at = datetime.utcnow()
            await session.commit()
        try:
            # Telegram has no separate kick API. ban + immediate unban removes the
            # member while allowing them to rejoin later; it is not a persistent ban.
            await bot.ban_chat_member(group_id, user_id)
            await bot.unban_chat_member(group_id, user_id, only_if_banned=True)
        except Exception:
            logger.exception("member removal failed chat_id=%s user_id=%s", group_id, user_id)
            return


    @router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
    async def new_member(event: ChatMemberUpdated) -> None:
        logger = logging.getLogger("tg_guard.member")
        group_id = event.chat.id
        if event.chat.type != "supergroup":
            logger.error("verification requires supergroup chat_id=%s type=%s; migrate the group", group_id, event.chat.type)
            return
        async with session_factory() as session:
            group = await session.scalar(select(ManagedGroup).where(ManagedGroup.chat_id == group_id))
        if group is None or not group.enabled or not group.verification_enabled:
            logger.warning("join ignored chat_id=%s enabled=%s verification=%s", group_id, getattr(group, "enabled", None), getattr(group, "verification_enabled", None))
            return
        user = event.new_chat_member.user
        if user.is_bot:
            return
        logger.info("join detected chat_id=%s user_id=%s", group_id, user.id)
        token = token_service.issue(user.id, ttl_seconds=300)
        digest = hashlib.sha256(token.value.encode()).hexdigest()
        async with session_factory() as session:
            session.add(GroupMember(chat_id=group_id, telegram_user_id=user.id, username=user.username or ""))
            session.add(Verification(chat_id=group_id, telegram_user_id=user.id, token_hash=digest, expires_at=token.expires_at, created_at=datetime.now(timezone.utc)))
            await session.commit()
        try:
            await bot.restrict_chat_member(group_id, user.id, permissions=ChatPermissions(can_send_messages=False))
            logger.info("restrict succeeded chat_id=%s user_id=%s", group_id, user.id)
            me = await bot.get_me()
            await bot.send_message(group_id, f"@{user.username or user.full_name}，请点击按钮私聊绑定 TG。", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="点击绑定 TG", url=build_start_link(me.username, token.value))]]))
            asyncio.create_task(remove_if_unverified(group_id, user.id, token.expires_at))
        except TelegramBadRequest as exc:
            logger.error("new-member Telegram API rejected chat_id=%s user_id=%s: %s", group_id, user.id, exc.message)
            try:
                await bot.send_message(group_id, "新人验证需要超级群组。请管理员先将本群升级为超级群组。")
            except Exception:
                pass
            return
        except Exception as exc:
            logger.exception("new-member handling failed chat_id=%s user_id=%s error=%s", group_id, user.id, type(exc).__name__)
            try:
                await bot.send_message(group_id, f"无法完成新成员验证：{type(exc).__name__}，已保持当前限制状态。")
            except Exception:
                pass
            return


    @router.message(Command("admin"))
    async def admin_command(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        await message.answer(panel_text(), reply_markup=panel_keyboard())

    @router.message(F.text == "添加当前群组")
    async def add_current_group(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        if message.chat.type != "supergroup":
            await message.answer("添加失败：当前是普通群组。请先升级为超级群组，Telegram 才支持禁言和移除成员。", reply_markup=panel_keyboard())
            return
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            me = await bot.get_me()
            bot_member = await bot.get_chat_member(message.chat.id, me.id)
        except Exception as exc:
            await message.answer(f"无法验证群组权限：{type(exc).__name__}")
            return
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            await message.answer("只有当前群组管理员或群主可以添加群组。")
            return
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            await message.answer("添加失败：请先将机器人设为群组管理员，并开启限制成员、删除消息等必要权限。")
            return
        async with session_factory() as session:
            row = await session.scalar(select(ManagedGroup).where(ManagedGroup.chat_id == message.chat.id))
            if row is None:
                session.add(ManagedGroup(
                    chat_id=message.chat.id,
                    title=message.chat.title or "",
                    added_by=message.from_user.id,
                    verification_enabled=True,
                    cleanup_mode="dry_run",
                ))
                setup_note = "新人验证已默认开启；运行模式默认为 dry-run，请在“运行模式”中明确切换自动移除。"
            else:
                row.title = message.chat.title or row.title
                row.enabled = True
                row.verification_enabled = True
                setup_note = "新人验证已开启；当前运行模式保持原配置。"
            await session.commit()
        await message.answer(f"已添加当前群组：{message.chat.title or message.chat.id}\n群组 ID：{message.chat.id}\n机器人管理员权限验证通过。\n{setup_note}", reply_markup=panel_keyboard())


    @router.message(F.text == "被移除的用户")
    async def removed_panel(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        await message.answer("被移除的用户\n\n点击“查看被移除用户”查看当前群组记录。", reply_markup=removed_keyboard())

    @router.message(F.text == "查看被移除用户")
    async def removed_list(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        async with session_factory() as session:
            rows = (await session.scalars(select(GroupMember).where(GroupMember.removed_at.is_not(None)).order_by(GroupMember.removed_at.desc()).limit(50))).all()
        await message.answer(removed_text(rows), reply_markup=removed_keyboard())


    @router.message(F.text == "用户 TG 绑定")
    async def tg_binding_settings(message: Message, state: FSMContext) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        await state.clear(); await state.set_state(TgBindingSettings.login_url)
        await message.answer("用户 TG 绑定设置\n\n请输入妙妙屋 X 登录页面地址（必须是 https:// 开头）。")

    @router.message(TgBindingSettings.login_url)
    async def tg_binding_login_url(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value.startswith("https://"):
            await message.answer("地址必须以 https:// 开头，请重新输入。")
            return
        await state.update_data(binding_login_url=value)
        await state.set_state(TgBindingSettings.bot_username)
        await message.answer("请输入官方 Telegram 机器人用户名，必须以 @ 或 _bot 结尾，例如：abc_bot。")

    @router.message(TgBindingSettings.bot_username)
    async def tg_binding_bot_username(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{3,64}_bot", value, re.IGNORECASE):
            await message.answer("机器人用户名格式不正确，必须以 _bot 结尾，例如：abc_bot。")
            return
        data = dict(await state.get_data())
        data["binding_bot_username"] = value
        async with session_factory() as session:
            row = await session.scalar(select(AdminConfig).where(AdminConfig.chat_id == message.from_user.id))
            encrypted = crypto.encrypt(json.dumps(data, ensure_ascii=False))
            if row is None: session.add(AdminConfig(chat_id=message.from_user.id, encrypted_payload=encrypted))
            else: row.encrypted_payload = encrypted
            await session.commit()
        await state.clear()
        await message.answer(f"用户 TG 绑定设置已保存。\n登录地址：{data['binding_login_url']}\n官方机器人：@{value}\n\n用户将被提醒机器人用户名必须以 _bot 结尾。", reply_markup=panel_keyboard())

    @router.message(F.text == "妙妙屋 X 配置")
    async def mmwx_panel(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        await message.answer("妙妙屋 X 连接配置\n\n通过可视化向导配置 SSH、部署方式和数据库连接。\n密码不会显示，配置会加密保存。", reply_markup=mmwx_keyboard())

    @router.message(F.text.in_(MMWX_MENU))
    async def mmwx_menu_action(message: Message, state: FSMContext) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        label = message.text or ""
        if label == "返回主面板": await message.answer(panel_text(), reply_markup=panel_keyboard()); return
        if label in {"查看当前配置", "开始连接配置", "重新配置连接"}:
            if label != "查看当前配置":
                await state.clear()
            if label == "查看当前配置":
                async with session_factory() as session:
                    row = await session.scalar(select(AdminConfig).where(AdminConfig.chat_id == message.from_user.id))
                if row is None:
                    await message.answer("尚未配置妙妙屋 X。", reply_markup=mmwx_keyboard()); return
                data = json.loads(crypto.decrypt(row.encrypted_payload))
                await message.answer(f"当前配置\n主控：{data.get('ssh_host', '-')}\n部署方式：{data.get('deployment', '-')}\nSSH 端口：{data.get('ssh_port', '-')}\nSSH 用户：{data.get('ssh_user', '-')}\n数据库用户：{data.get('db_user', '-')}\n数据库：{data.get('db_type', '-')}\nMeow_bot：@{data.get('binding_bot_username', '未配置')}\n\n密码已隐藏。", reply_markup=mmwx_keyboard()); return
            await state.set_state(Wizard.ssh_host)
            await message.answer("妙妙屋 X 配置\n请输入主控 IP 或域名。")
            return
        if label == "Meow_bot":
            await state.clear(); await state.set_state(MMWXSettings.field)
            await state.update_data(field="binding_bot_username")
            await message.answer("Meow_bot 配置\n\n跳转地址将自动使用主控地址生成，不能单独修改。\n请输入机器人用户名，必须以 _bot 结尾，例如 abc_bot。")
            return
        fields = {"主控地址": ("ssh_host", "请输入主控 IP 或域名。"), "部署方式": ("deployment", "请输入 docker 或 script。"), "SSH 端口": ("ssh_port", "请输入 SSH 端口，例如 22。"), "SSH 只读用户": ("ssh_user", "请输入 SSH 只读用户名。"), "SSH 密码": ("ssh_password", "请输入 SSH 密码。"), "数据库用户": ("db_user", "请输入数据库用户名。"), "数据库密码": ("db_password", "请输入数据库密码。")}
        field, prompt = fields[label]
        await state.clear(); await state.set_state(MMWXSettings.field); await state.update_data(field=field)
        await message.answer(prompt)

    @router.message(MMWXSettings.field)
    async def mmwx_field_value(message: Message, state: FSMContext) -> None:
        data = dict(await state.get_data()); field = data.get("field"); value = (message.text or "").strip()
        if field == "binding_bot_username":
            value = value.lstrip("@")
            if not re.fullmatch(r"[A-Za-z0-9_]{3,64}_bot", value, re.IGNORECASE):
                await message.answer("机器人用户名必须以 _bot 结尾，例如 abc_bot。")
                return
        elif field == "deployment" and value not in {"docker", "script"}:
            await message.answer("部署方式只能是 docker 或 script。"); return
        elif field == "ssh_port" and (not value.isdigit() or not 1 <= int(value) <= 65535):
            await message.answer("SSH 端口必须是 1 到 65535。"); return
        async with session_factory() as session:
            row = await session.scalar(select(AdminConfig).where(AdminConfig.chat_id == message.from_user.id))
            current = json.loads(crypto.decrypt(row.encrypted_payload)) if row else {}
            current[field] = value
            if field == "ssh_host":
                current["binding_login_url"] = value if value.startswith(("http://", "https://")) else f"https://{value}"
            encrypted = crypto.encrypt(json.dumps(current, ensure_ascii=False))
            if row is None: session.add(AdminConfig(chat_id=message.from_user.id, encrypted_payload=encrypted))
            else: row.encrypted_payload = encrypted
            await session.commit()
        await state.clear(); await message.answer(f"{field} 已保存。", reply_markup=mmwx_keyboard())


    async def save(message: Message, state: FSMContext) -> None:
        data = dict(await state.get_data())
        async with session_factory() as session:
            row = await session.scalar(select(AdminConfig).where(AdminConfig.chat_id == message.from_user.id))
            encrypted = crypto.encrypt(json.dumps(data, ensure_ascii=False))
            if row is None: session.add(AdminConfig(chat_id=message.from_user.id, encrypted_payload=encrypted))
            else: row.encrypted_payload = encrypted
            await session.commit()
        await state.clear(); await message.answer("配置已加密保存。除密码外的连接参数会自动探测；下一步可执行 SSH 和数据库连通性验证。", reply_markup=panel_keyboard())

    @router.message(Wizard.ssh_host)
    async def ssh_host(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value: await message.answer("主控 IP 或域名不能为空。"); return
        await state.update_data(ssh_host=value)
        await state.set_state(Wizard.deployment)
        await message.answer("妙妙屋 X 配置向导（2/7）\n请选择部署方式：docker 或 script。")

    @router.message(Wizard.deployment)
    async def deployment(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip().lower()
        if value not in {"docker", "script"}:
            await message.answer("请输入 docker 或 script。")
            return
        await state.update_data(deployment=value)
        await state.set_state(Wizard.ssh_port)
        await message.answer("妙妙屋 X 配置向导（3/8）\n请输入 SSH 端口，例如 22。")

    @router.message(Wizard.ssh_port)
    async def ssh_port(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value.isdigit() or not 1 <= int(value) <= 65535:
            await message.answer("SSH 端口必须是 1 到 65535 的数字。")
            return
        await state.update_data(ssh_port=value)
        await state.set_state(Wizard.ssh_user)
        await message.answer("妙妙屋 X 配置向导（4/8）\n请输入 SSH 只读用户名。")

    @router.message(Wizard.ssh_user)
    async def ssh_user(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value:
            await message.answer("用户名不能为空，请重新输入。")
            return
        await state.update_data(ssh_user=value)
        await state.set_state(Wizard.ssh_password)
        await message.answer("妙妙屋 X 配置向导（5/8）\n请输入 SSH 密码。输入后会尝试删除原消息。")

    @router.message(Wizard.ssh_password)
    async def ssh_password(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value:
            await message.answer("密码不能为空，请重新输入。")
            return
        data = dict(await state.get_data())
        progress = await message.answer("正在检测 SSH 连接，请稍候……")
        try:
            discovered = await discover_database(
                host=data["ssh_host"], username=data["ssh_user"], password=value,
                port=int(data["ssh_port"]), deployment=data["deployment"]
            )
        except DiscoveryError as exc:
            await progress.edit_text(f"SSH/数据库检测失败：{exc}\n请检查 IP、端口、用户名、密码和部署方式后重试。")
            return
        await state.update_data(
            ssh_password=value,
            db_type=discovered.kind,
            db_path=discovered.path,
            db_host=discovered.host,
            db_port=discovered.port,
            discovery_evidence=discovered.evidence,
        )
        try:
            await message.delete()
        except Exception:
            pass
        await state.set_state(Wizard.db_user)
        await message.answer(
            f"SSH 连接成功，已通过主控验证。\n主控返回字段：{discovered.evidence[:500]}\n"
            f"已自动识别数据库：{discovered.kind}\n"
            f"数据库路径：{discovered.path}\n"
            "妙妙屋 X 配置向导（6/9）\n请输入数据库用户名。输入 1 使用默认值 mmwx。"
        )

    @router.message(Wizard.db_user)
    async def db_user(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if value == "1": value = "mmwx"
        if not value: await message.answer("用户名不能为空；输入 1 使用默认值 mmwx。"); return
        await state.update_data(db_user=value)
        await state.set_state(Wizard.db_password)
        await message.answer("妙妙屋 X 配置向导（7/9）\n请输入数据库密码。输入 1 使用默认值 mmwx。")

    @router.message(Wizard.db_password)
    async def db_password(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value: await message.answer("密码不能为空；输入 1 使用默认值 mmwx。"); return
        if value == "1": value = "mmwx"
        await state.update_data(db_password=value)
        try: await message.delete()
        except Exception: pass
        data = dict(await state.get_data())
        try:
            detected_table = await discover_user_table(data)
        except DiscoveryError as exc:
            await message.answer(f"数据库表名自动获取失败：{exc}\n请检查数据库账号密码和只读权限后重试。")
            return
        await state.update_data(table=detected_table)
        await save(message, state)
        await message.answer(f"已自动获取用户主表：public.{detected_table}", reply_markup=panel_keyboard())
    @router.message(Wizard.table)
    async def table_legacy(message: Message, state: FSMContext) -> None:
        await message.answer("用户表名已自动获取，无需手动输入。")

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext) -> None:
        await state.clear(); await message.answer("已取消配置向导。", reply_markup=panel_keyboard())

    @router.message(F.text == "运行模式")
    async def mode_panel(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        async with session_factory() as session:
            groups = (await session.scalars(select(ManagedGroup))).all()
            current = groups[0].cleanup_mode if groups else "dry_run"
        await message.answer(mode_text(current), reply_markup=mode_keyboard())

    @router.message(F.text.in_(MODE_MENU))
    async def mode_action(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        label = message.text or ""
        if label == "返回主面板": await message.answer(panel_text(), reply_markup=panel_keyboard()); return
        mode = {"仅报告（dry-run）": "dry_run", "仅查询不处理": "query_only", "自动移出成员": "auto_remove"}[label]
        async with session_factory() as session:
            groups = (await session.scalars(select(ManagedGroup))).all()
            for group in groups: group.cleanup_mode = mode
            await session.commit()
        if mode == "auto_remove":
            text = "已切换为自动移除模式。系统仍会保护管理员、群主、机器人和白名单；查询失败时禁止移除。"
        else: text = f"已切换为{label}。"
        await message.answer(text, reply_markup=mode_keyboard())

    @router.message(F.text == "群组设置")
    async def group_panel(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        await message.answer(group_text(), reply_markup=group_keyboard())

    @router.message(F.text.in_(GROUP_MENU))
    async def group_action(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        label = message.text or ""
        if label == "返回主面板": await message.answer(panel_text(), reply_markup=panel_keyboard()); return
        if label == "验证机器人权限":
            if message.chat.type not in {"group", "supergroup"}: text = "请在目标群组内点击此按钮。"
            else:
                me = await bot.get_me(); m = await bot.get_chat_member(message.chat.id, me.id)
                text = f"机器人权限状态：{m.status}"
            await message.answer(text, reply_markup=group_keyboard()); return
        if message.chat.type != "supergroup":
            await message.answer("当前群组是普通群组。Telegram 禁言功能只支持超级群组，请先将群组升级为超级群组后再开启新人验证。", reply_markup=group_keyboard())
            return
        async with session_factory() as session:
            group = await session.scalar(select(ManagedGroup).where(ManagedGroup.chat_id == message.chat.id))
            if group is None:
                await message.answer("请先点击“添加当前群组”。", reply_markup=group_keyboard()); return
            if label == "开启新人验证": group.verification_enabled = True
            elif label == "关闭新人验证": group.verification_enabled = False
            await session.commit()
        await message.answer(f"已更新：{label}", reply_markup=group_keyboard())


    @router.message(F.text == "任务")
    async def task_panel_button(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        async with session_factory() as session:
            groups = (await session.scalars(select(ManagedGroup))).all()
            mode = groups[0].cleanup_mode if groups else "dry_run"
        await message.answer(task_text(mode, tasks.enabled), reply_markup=task_keyboard())


    @router.message(Command("task"))
    async def task_command(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        async with session_factory() as session:
            groups = (await session.scalars(select(ManagedGroup))).all()
            mode = groups[0].cleanup_mode if groups else "dry_run"
        await message.answer(task_text(mode, tasks.enabled), reply_markup=task_keyboard())

    @router.message(F.text.in_(TASK_MENU))
    async def task_action(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        label = message.text or ""
        if label == "返回主面板":
            await message.answer(panel_text(), reply_markup=panel_keyboard()); return
        async with session_factory() as session:
            groups = (await session.scalars(select(ManagedGroup).where(ManagedGroup.enabled.is_(True)))).all()
        mode = groups[0].cleanup_mode if groups else "dry_run"
        if label == "开启任务":
            tasks.enabled = True
            text = "已开启清理任务。"
        elif label == "暂停任务":
            tasks.enabled = False
            text = "已暂停清理任务。"
        elif label == "立即执行清理":
            report = await tasks.run(configured=bool(groups), mode=mode, members=[])
            if groups:
                lines = ["群聊成员绑定核对报告"]
                for group in groups:
                    try:
                        admins = await bot.get_chat_administrators(group.chat_id)
                        protected_ids = {member.user.id for member in admins}
                        protected_ids.add((await bot.get_me()).id)
                        async with session_factory() as member_session:
                            tracked = (await member_session.scalars(select(GroupMember).where(GroupMember.chat_id == group.chat_id, GroupMember.removed_at.is_(None)))).all()
                            config_row = await member_session.scalar(select(AdminConfig).where(AdminConfig.chat_id == message.from_user.id))
                        if config_row is None:
                            raise RuntimeError("未找到妙妙屋 X 配置")
                        data = json.loads(crypto.decrypt(config_row.encrypted_payload))
                        ids = [member.telegram_user_id for member in tracked]
                        mmwx = await query_mmwx_users(data, ids)
                        lines.append(f"群组：{group.title or group.chat_id}")
                        lines.append(f"已记录成员数：{len(tracked)}")
                        for tracked_member in tracked:
                            row = mmwx.get(tracked_member.telegram_user_id)
                            bound = row is not None
                            status = "已绑定" if bound else "未绑定"
                            action = "保留"
                            if not bound and tracked_member.telegram_user_id not in protected_ids:
                                if mode == "auto_remove":
                                    # Telegram's kick operation is ban followed by immediate unban.
                                    await bot.ban_chat_member(group.chat_id, tracked_member.telegram_user_id)
                                    await bot.unban_chat_member(group.chat_id, tracked_member.telegram_user_id, only_if_banned=True)
                                    action = "已移出"
                                else:
                                    action = "待移除"
                            lines.append(f"@{tracked_member.username or '无用户名'} | Telegram ID：{tracked_member.telegram_user_id} | 妙妙屋 X tgid：{row.telegram_id if row else '未绑定'} | {status} | {action}")
                        lines.append("管理员、群主、机器人和查询失败对象不会被移除。")
                    except Exception as exc:
                        lines.append(f"群组：{group.title or group.chat_id} | 查询失败：{type(exc).__name__} | 不执行移除")
                report.detail = "\n".join(lines) + f"\n运行模式：{mode}"
            text = f"查询任务已执行。\n{report.detail}"
        elif label == "查看查询报告": text = tasks.text()
        elif label == "任务设置":
            text = task_text(mode, tasks.enabled)
        await message.answer(text, reply_markup=task_keyboard())


    @router.message(F.text.in_(MENU - {"妙妙屋 X 配置", "任务", "用户 TG 绑定"}))
    async def menu_action(message: Message) -> None:
        if not allowed(message): await message.answer("无权限。"); return
        label = message.text or ""
        if label == "添加当前群组":
            await message.answer("请在目标群组内点击“添加当前群组”。机器人会通过 Telegram API 验证管理员权限。", reply_markup=panel_keyboard())
            return
        elif label == "清理任务":
            async with session_factory() as session:
                groups = (await session.scalars(select(ManagedGroup))).all()
                mode = groups[0].cleanup_mode if groups else "dry_run"
            await message.answer(task_text(mode, tasks.enabled), reply_markup=task_keyboard())
            return
        if label == "系统状态": result = await status_provider()
        elif label == "我的群组":
            async with session_factory() as session:
                groups = (await session.scalars(select(ManagedGroup).order_by(ManagedGroup.id))).all()
            result = "我的群组\n" + ("\n".join(f"• {g.title or g.chat_id} ({g.chat_id})：{'开启' if g.enabled else '关闭'}" for g in groups) if groups else "暂无已添加群组")
        elif label == "被移除的用户": result = "请点击主面板的“被移除的用户”查看记录。"
        elif label == "群组设置": result = "请点击主面板的“群组设置”进入可视化设置。"
        elif label == "清理任务":
            result = "请点击主面板的“清理任务”进入任务控制面板。"
        elif label == "审核记录": result = "暂无可展示的审核记录"
        elif label == "添加当前群组": result = "请在目标群组内点击“添加当前群组”。机器人会通过 Telegram API 验证你的管理员身份和自身管理员权限。"
        else: result = "发送 /admin 返回主面板。"
        await message.answer(result, reply_markup=panel_keyboard())
    return router
