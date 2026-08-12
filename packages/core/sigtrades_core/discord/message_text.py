"""从 Discord Gateway MESSAGE_CREATE 载荷提取可解析文本。"""

from __future__ import annotations

from typing import Any, Dict, List


def _append(parts: List[str], text: Any) -> None:
    if not isinstance(text, str):
        return
    val = text.strip()
    if val:
        parts.append(val)


def extract_discord_message_text(data: Dict[str, Any]) -> str:
    """合并 content 与 embeds（title/description/fields/footer）为纯文本。"""
    parts: List[str] = []
    _append(parts, data.get("content"))

    for embed in data.get("embeds") or []:
        if not isinstance(embed, dict):
            continue
        _append(parts, embed.get("title"))
        _append(parts, embed.get("description"))
        for field in embed.get("fields") or []:
            if not isinstance(field, dict):
                continue
            name = (field.get("name") or "").strip()
            value = (field.get("value") or "").strip()
            if name and value:
                parts.append(f"{name}\n{value}")
            else:
                _append(parts, value or name)
        footer = embed.get("footer")
        if isinstance(footer, dict):
            _append(parts, footer.get("text"))

    return "\n".join(parts).strip()
