"""
True Classic Bot - Embed Script Engine
Author: Aljay Leodones
Organization: True Classic
"""

import copy
import datetime
import json
from typing import Any, Dict, List, Optional
import discord
from utils import embed_builder

class EmbedScript:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.content: Optional[str] = None
        self.buttons: List[Dict[str, Any]] = []
        self.channels: List[discord.TextChannel] = []
        self.embeds: List[Dict[str, Any]] = [self._default_embed_state()]

    def _default_embed_state(self) -> Dict[str, Any]:
        return {
            "title": "New Embed",
            "description": "Use edit buttons to set content.",
            "color": embed_builder.COLOR_BRAND,
            "url": None,
            "author_name": None,
            "author_icon": None,
            "author_url": None,
            "image_url": None,
            "thumbnail_url": None,
            "footer_text": None,
            "footer_icon": None,
            "fields": []
        }

    def _resolve_text(self, text: Optional[str], member: Optional[discord.Member] = None) -> Optional[str]:
        if not text or "{" not in text:
            return text

        guild = member.guild if member else None
        
        replacements = {
            "{user_mention}": member.mention if member else "(member mention)",
            "{user_name}": member.display_name if member else "(member name)",
            "{server_name}": guild.name if guild else "(server name)",
            "{member_count}": str(guild.member_count) if guild else "0",
            "{date_now}": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        }

        for key, val in replacements.items():
            text = text.replace(key, val)
        return text

    def to_dict(self) -> Dict[str, Any]:
        """Serializes complete message state for DB storage or JSON export."""
        return {
            "user_id": self.user_id,
            "content": self.content,
            "embeds": copy.deepcopy(self.embeds),
            "buttons": copy.deepcopy(self.buttons),
            "target_channel_ids": [c.id for c in self.channels if hasattr(c, "id")],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbedScript":
        instance = cls(user_id=data.get("user_id", 0))
        instance.content = data.get("content")
        instance.embeds = copy.deepcopy(data.get("embeds", [instance._default_embed_state()]))
        instance.buttons = copy.deepcopy(data.get("buttons", []))
        return instance

    def build_discord_embeds(self, member: Optional[discord.Member] = None) -> List[discord.Embed]:
        discord_embeds = []
        for state in self.embeds[:10]:  # Discord limit: max 10 embeds per message
            title = self._resolve_text(state.get("title"), member)
            desc = self._resolve_text(state.get("description"), member)
            url = state.get("url")
            color = state.get("color", embed_builder.COLOR_BRAND)

            embed = discord.Embed(
                title=title,
                description=desc,
                url=url if url else None,
                color=color
            )

            if state.get("author_name"):
                embed.set_author(
                    name=self._resolve_text(state["author_name"], member),
                    icon_url=state.get("author_icon") or None,
                    url=state.get("author_url") or None
                )
            if state.get("image_url"):
                embed.set_image(url=state["image_url"])
            if state.get("thumbnail_url"):
                embed.set_thumbnail(url=state["thumbnail_url"])
            if state.get("footer_text"):
                embed.set_footer(
                    text=self._resolve_text(state["footer_text"], member),
                    icon_url=state.get("footer_icon") or None
                )
            for field in state.get("fields", []):
                fname = self._resolve_text(field.get("name"), member)
                fval = self._resolve_text(field.get("value"), member)
                embed.add_field(
                    name=fname or "\u200b",
                    value=fval or "\u200b",
                    inline=field.get("inline", True)
                )
            discord_embeds.append(embed)
        return discord_embeds
