"""
True Classic Bot - Embed Builder Utilities
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc
"""

import datetime
import discord

COLOR_BRAND   = 0x00C9A7  # Teal / Brand Accent
COLOR_SUCCESS = 0x2ECC71  # Emerald Green
COLOR_ERROR   = 0xE74C3C  # Crimson Red
COLOR_WARNING = 0xF1C40F  # Amber Yellow
COLOR_INFO    = 0x3498DB  # Sapphire Blue

SECTION_PREFIX = "◈"
ITEM_PREFIX = "▸"
SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

STATUS_OK   = "✅"
STATUS_WARN = "⚠️"
STATUS_ERR  = "❌"

BOT_NAME = "True Classic"
BOT_TAGLINE = "Community Operations Bot"
BOT_DETAILS = "Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc"

def base_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = COLOR_BRAND,
    footer_text: str | None = None,
    timestamp: bool = True
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    if timestamp:
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    
    formatted_footer = footer_text or f"{BOT_NAME} • {BOT_TAGLINE}"
    embed.set_footer(text=formatted_footer)
    return embed

def success_embed(title: str, description: str | None = None, footer_text: str | None = None) -> discord.Embed:
    return base_embed(title=f"{STATUS_OK} {title}", description=description, color=COLOR_SUCCESS, footer_text=footer_text)

def error_embed(title: str, description: str | None = None, footer_text: str | None = None) -> discord.Embed:
    return base_embed(title=f"{STATUS_ERR} {title}", description=description, color=COLOR_ERROR, footer_text=footer_text)

def warning_embed(title: str, description: str | None = None, footer_text: str | None = None) -> discord.Embed:
    return base_embed(title=f"{STATUS_WARN} {title}", description=description, color=COLOR_WARNING, footer_text=footer_text)

def info_embed(title: str, description: str | None = None, footer_text: str | None = None) -> discord.Embed:
    return base_embed(title=f"ℹ️ {title}", description=description, color=COLOR_INFO, footer_text=footer_text)
