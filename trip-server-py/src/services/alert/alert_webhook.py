"""
Webhook 通知器

支持多种 IM 格式：飞书 / Slack / 钉钉 / 企业微信 / 自定义
失败 retry 3 次（1s/3s/9s 指数退避）
失败只 warn log，不抛错
"""

import httpx
import asyncio
from dataclasses import dataclass
from typing import Optional
import logging

from src.config.settings import settings
from src.services.alert.alert_detector import AlertCheckResult

log = logging.getLogger("alert")


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    attempts: int
    error: Optional[str] = None


class WebhookNotifier:
    """Webhook 通知器"""

    async def send(self, check: AlertCheckResult) -> SendResult:
        """
        发送告警通知
        
        Args:
            check: 告警检测结果
            
        Returns:
            SendResult: 发送结果
        """
        webhook_url = settings.alert_webhook_url
        if not webhook_url:
            return SendResult(success=False, attempts=0, error="webhook_url 未配置")

        webhook_type = settings.alert_webhook_type
        dashboard_url = settings.dashboard_url
        payload = self.format_payload(webhook_type, check, dashboard_url)
        max_attempts = 3

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_attempts):
                try:
                    response = await client.post(
                        webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    if response.is_success:
                        log.info(f"告警发送成功: type={webhook_type}, attempt={attempt + 1}, status={response.status_code}")
                        return SendResult(success=True, attempts=attempt + 1)
                    
                    log.warning(f"webhook 返回非 200: type={webhook_type}, attempt={attempt + 1}, status={response.status_code}")
                except Exception as e:
                    error_msg = str(e)
                    if attempt == max_attempts - 1:
                        log.error(f"webhook 发送最终失败: err={error_msg}, type={webhook_type}, attempts={max_attempts}")
                        return SendResult(success=False, attempts=max_attempts, error=error_msg)
                    log.warning(f"webhook 发送失败，将重试: err={error_msg}, attempt={attempt + 1}")
                
                # 指数退避：1s, 3s, 9s
                await asyncio.sleep(1 * (3 ** attempt))

        return SendResult(success=False, attempts=max_attempts, error="all retries failed")

    def format_payload(self, webhook_type: str, check: AlertCheckResult, dashboard_url: str) -> dict:
        """
        格式化告警消息
        
        Args:
            webhook_type: webhook 类型
            check: 告警检测结果
            dashboard_url: dashboard URL
            
        Returns:
            dict: 格式化的消息体
        """
        title = "⚠️ Feedback 满意率告警"
        summary = check.reason
        
        # 格式化最近差评
        comments_list = check.stats.get("recentDownComments", [])
        comments_lines = []
        for c in comments_list:
            tag_str = ""
            tags = c.get("tags")
            if tags and isinstance(tags, list) and len(tags) > 0:
                tag_str = f" [{', '.join(tags)}]"
            comments_lines.append(f"- {c.get('comment', '')}{tag_str}")
        comments = "\n".join(comments_lines) if comments_lines else "（无评论）"
        
        link = f"{dashboard_url}/admin/feedback"

        if webhook_type == "feishu":
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": title}},
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{summary}**\n\n最近差评：\n{comments}",
                            },
                        },
                        {
                            "tag": "action",
                            "actions": [
                                {
                                    "tag": "button",
                                    "text": {"tag": "plain_text", "content": "查看 Dashboard"},
                                    "type": "primary",
                                    "url": link,
                                }
                            ],
                        },
                    ],
                },
            }
        elif webhook_type == "slack":
            return {
                "text": title,
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{summary}*\n\n最近差评：\n{comments}"},
                    },
                    {
                        "type": "actions",
                        "elements": [{"type": "button", "text": {"type": "plain_text", "text": "查看 Dashboard"}, "url": link}],
                    },
                ],
            }
        elif webhook_type == "dingtalk":
            return {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"**{summary}**\n\n最近差评：\n{comments}\n\n[查看 Dashboard]({link})",
                },
            }
        elif webhook_type == "wecom":
            return {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"**{title}**\n\n{summary}\n\n最近差评：\n{comments}",
                },
            }
        else:
            # custom / 默认
            return {
                "title": title,
                "summary": summary,
                "comments": comments_list,
                "stats": check.stats,
                "dashboardUrl": link,
            }


# 单例
webhook_notifier = WebhookNotifier()
