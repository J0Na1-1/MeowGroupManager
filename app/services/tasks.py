from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass
class TaskReport:
    status: str = "未执行"
    detail: str = ""
    created_at: datetime | None = None


class TaskController:
    """Small persistent-process task controller; destructive actions stay disabled."""

    def __init__(self) -> None:
        self.enabled = False
        self.last_report = TaskReport()

    async def run(self, configured: bool, mode: str = "dry_run", members: list[dict[str, object]] | None = None) -> TaskReport:
        now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        labels = {"dry_run": "dry-run", "query_only": "仅查询", "auto_remove": "自动移除"}
        mode_label = labels.get(mode, mode)
        if not configured:
            report = TaskReport("失败", f"未找到妙妙屋 X 配置；运行模式：{mode_label}。未执行成员处理。", now)
        else:
            detail = f"运行模式：{mode_label}\n"
            if members:
                detail += "\n".join(
                    f"@{m.get('username') or '无用户名'} | Telegram ID：{m.get('telegram_id')} | "
                    f"妙妙屋 X tgid：{m.get('mmwx_telegram_id', '未查询')} | {m.get('status', '未判定')}"
                    for m in members
                )
                detail += "\n"
            if mode == "auto_remove":
                detail += "符合条件的成员将被移出群组；不会永久拉黑。管理员、群主、机器人、白名单和查询失败对象均不处理。"
            elif mode == "query_only":
                detail += "仅核对绑定状态，不移除成员。"
            else:
                detail += "仅生成报告，不移除成员。"
            report = TaskReport("完成", detail, now)
        self.last_report = report
        return report

    def text(self) -> str:
        report = self.last_report
        when = report.created_at.isoformat(timespec="seconds") if report.created_at else "无"
        return f"查询报告\n状态：{report.status}\n时间：{when}\n{report.detail or '暂无报告。'}"
