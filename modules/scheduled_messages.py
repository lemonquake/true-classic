"""
True Classic Bot - Scheduled Messages Module
Author: Aljay Leodones
Organization: True Classic
"""

import asyncio
import datetime
import json
import zoneinfo
from typing import Dict, List, Optional
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select, Modal, TextInput, ChannelSelect
from discord import TextStyle, ButtonStyle, ChannelType

import config
from utils import embed_builder
from core.embed_script import EmbedScript

TIMEZONE_CHOICES = {
    "UTC": "UTC",
    "US/Eastern (EST/EDT)": "America/New_York",
    "US/Central (CST/CDT)": "America/Chicago",
    "US/Mountain (MST/MDT)": "America/Denver",
    "US/Pacific (PST/PDT)": "America/Los_Angeles",
    "Europe/London (GMT/BST)": "Europe/London",
    "Europe/Paris (CET/CEST)": "Europe/Paris",
    "Asia/Manila (PHT)": "Asia/Manila",
    "Asia/Singapore (SGT)": "Asia/Singapore",
    "Asia/Tokyo (JST)": "Asia/Tokyo",
    "Australia/Sydney (AEST/AEDT)": "Australia/Sydney",
}

MINUTE_INTERVALS = ["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"]

class SecuredView(View):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        if not has_role:
            await interaction.response.send_message(
                embed=embed_builder.error_embed(
                    "Permission Denied",
                    "You do not have required permissions to access scheduled messages."
                ),
                ephemeral=True
            )
            return False
        return True

async def get_scheduled_messages(bot, guild_id: int, status: str = "pending") -> List[Dict]:
    if status == "all":
        rows = await bot.database.fetchall(
            "SELECT * FROM scheduled_messages WHERE guild_id = ? ORDER BY id DESC LIMIT 25",
            (guild_id,)
        )
    else:
        rows = await bot.database.fetchall(
            "SELECT * FROM scheduled_messages WHERE guild_id = ? AND status = ? ORDER BY scheduled_time ASC",
            (guild_id, status)
        )
    return [dict(r) for r in rows]

async def save_scheduled_message(
    bot,
    guild_id: int,
    user_id: int,
    channel_ids: List[int],
    payload: Dict,
    scheduled_utc_iso: str,
    timezone_label: str
) -> int:
    channel_ids_json = json.dumps(channel_ids)
    payload_json = json.dumps(payload)
    
    cursor = await bot.database.execute(
        """
        INSERT INTO scheduled_messages (guild_id, user_id, channel_ids, payload, scheduled_time, timezone_name, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (guild_id, user_id, channel_ids_json, payload_json, scheduled_utc_iso, timezone_label)
    )
    return cursor.lastrowid

async def update_scheduled_message_time(bot, message_id: int, scheduled_utc_iso: str, timezone_label: str):
    await bot.database.execute(
        """
        UPDATE scheduled_messages
        SET scheduled_time = ?, timezone_name = ?
        WHERE id = ?
        """,
        (scheduled_utc_iso, timezone_label, message_id)
    )

async def update_scheduled_message_channels(bot, message_id: int, channel_ids: List[int]):
    channel_ids_json = json.dumps(channel_ids)
    await bot.database.execute(
        "UPDATE scheduled_messages SET channel_ids = ? WHERE id = ?",
        (channel_ids_json, message_id)
    )

async def cancel_scheduled_message(bot, message_id: int):
    await bot.database.execute(
        "UPDATE scheduled_messages SET status = 'cancelled' WHERE id = ?",
        (message_id,)
    )

# Hub View for Scheduled Messages

class ScheduledMessagesHubView(SecuredView):
    def __init__(self, bot, parent_panel_view=None, draft_payload=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.parent_panel_view = parent_panel_view
        self.draft_payload = draft_payload

    async def build_hub_embed(self, guild: discord.Guild) -> discord.Embed:
        pending = await get_scheduled_messages(self.bot, guild.id, status="pending")
        
        embed = embed_builder.base_embed(
            title=f"📅 Scheduled Messages Manager ({len(pending)} Pending)",
            description="Manage persistently scheduled broadcasts, channels, and dispatch timing.",
            color=embed_builder.COLOR_BRAND
        )

        if not pending:
            embed.add_field(
                name="📋 Pending Schedules",
                value="*No pending scheduled messages found.* Click **➕ Schedule New** to create one.",
                inline=False
            )
        else:
            lines = []
            for item in pending[:10]:
                msg_id = item["id"]
                tz_label = item.get("timezone_name", "UTC")
                utc_str = item["scheduled_time"]
                
                # Format UTC to readable local representation
                try:
                    dt_utc = datetime.datetime.fromisoformat(utc_str)
                    readable_utc = dt_utc.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    readable_utc = utc_str

                ch_ids = json.loads(item["channel_ids"])
                ch_mentions = [f"<#{cid}>" for cid in ch_ids]
                ch_str = ", ".join(ch_mentions) if ch_mentions else "(no channels)"

                payload = json.loads(item["payload"])
                content_preview = payload.get("content") or "(embed broadcast)"
                if len(content_preview) > 50:
                    content_preview = content_preview[:47] + "..."

                lines.append(
                    f"**ID #{msg_id}** • {readable_utc} ({tz_label})\n"
                    f"▸ **Channels:** {ch_str}\n"
                    f"▸ **Preview:** {content_preview}\n"
                )
            
            embed.add_field(name="📋 Active Pending Schedules", value="\n".join(lines), inline=False)

        if self.draft_payload:
            embed.add_field(
                name="✨ Draft Ready from Embed Editor",
                value="You have an active draft from Embed Editor ready to schedule!",
                inline=False
            )

        return embed

    @discord.ui.button(label="➕ Schedule New", style=ButtonStyle.green, row=0)
    async def schedule_new_btn(self, interaction: discord.Interaction, button: Button):
        # Open schedule creation wizard
        wizard = ScheduleWizardView(self.bot, self, draft_payload=self.draft_payload)
        embed = embed_builder.info_embed(
            "Schedule New Broadcast (Step 1/3)",
            "Select target text channels where this scheduled message should be posted:"
        )
        await interaction.response.edit_message(embed=embed, view=wizard)

    @discord.ui.button(label="✏️ Manage / Edit", style=ButtonStyle.blurple, row=0)
    async def manage_btn(self, interaction: discord.Interaction, button: Button):
        pending = await get_scheduled_messages(self.bot, interaction.guild.id, status="pending")
        if not pending:
            await interaction.response.send_message("No pending scheduled messages to edit.", ephemeral=True)
            return

        options = []
        for item in pending[:25]:
            msg_id = item["id"]
            tz = item.get("timezone_name", "UTC")
            utc_time = item["scheduled_time"][:16].replace("T", " ")
            options.append(
                discord.SelectOption(
                    label=f"ID #{msg_id} - {utc_time} ({tz})",
                    value=str(msg_id),
                    description=f"Edit channels, time, or cancel ID #{msg_id}"
                )
            )

        view = SecuredView(timeout=180)
        select = Select(placeholder="Select a scheduled message to edit...", options=options)

        async def select_cb(inter: discord.Interaction):
            selected_id = int(select.values[0])
            edit_view = ScheduleEditView(self.bot, selected_id, self)
            embed = await edit_view.build_embed(inter.guild)
            await inter.response.edit_message(embed=embed, view=edit_view)

        select.callback = select_cb
        view.add_item(select)

        cancel_b = Button(label="Cancel", style=ButtonStyle.red)
        async def cancel_cb(inter: discord.Interaction):
            embed = await self.build_hub_embed(inter.guild)
            await inter.response.edit_message(embed=embed, view=self)
        cancel_b.callback = cancel_cb
        view.add_item(cancel_b)

        await interaction.response.edit_message(
            embed=embed_builder.info_embed("Select Scheduled Message", "Choose a scheduled message from the dropdown below to edit or cancel:"),
            view=view
        )

    @discord.ui.button(label="🔄 Refresh Hub", style=ButtonStyle.grey, row=0)
    async def refresh_btn(self, interaction: discord.Interaction, button: Button):
        embed = await self.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅ Back to Panel", style=ButtonStyle.blurple, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: Button):
        if self.parent_panel_view:
            await self.parent_panel_view.show_panel(interaction)
        else:
            await interaction.response.send_message("Hub closed.", ephemeral=True)


# Schedule Creation Wizard (Step 1: Channels -> Step 2: Timezone & Time -> Step 3: Confirm)

class ScheduleWizardView(SecuredView):
    def __init__(self, bot, hub_view, draft_payload=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.hub_view = hub_view
        self.draft_payload = draft_payload
        self.selected_channels = []
        self.timezone_name = "UTC"
        self.iana_tz = "UTC"

        c_select = ChannelSelect(
            placeholder="Select target text channels (up to 5)...",
            min_values=1,
            max_values=5,
            channel_types=[ChannelType.text, ChannelType.news]
        )
        c_select.callback = self.channel_cb
        self.add_item(c_select)

    async def channel_cb(self, interaction: discord.Interaction):
        self.selected_channels = [int(val) for val in interaction.data["values"]]
        
        # Move to Step 2: Select Timezone
        tz_view = ScheduleTimezoneView(self.bot, self.hub_view, self.selected_channels, self.draft_payload)
        embed = embed_builder.info_embed(
            "Schedule New Broadcast (Step 2/3)",
            f"Selected Channels: {', '.join([f'<#{cid}>' for cid in self.selected_channels])}\n\n"
            "Now pick your preferred Timezone from the dropdown below:"
        )
        await interaction.response.edit_message(embed=embed, view=tz_view)

    @discord.ui.button(label="Cancel", style=ButtonStyle.red, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        embed = await self.hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.hub_view)


class ScheduleTimezoneView(SecuredView):
    def __init__(self, bot, hub_view, selected_channels, draft_payload=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.hub_view = hub_view
        self.selected_channels = selected_channels
        self.draft_payload = draft_payload

        options = []
        for label, iana in TIMEZONE_CHOICES.items():
            options.append(discord.SelectOption(label=label, value=label))

        tz_select = Select(placeholder="Choose Timezone...", options=options, min_values=1, max_values=1)
        tz_select.callback = self.tz_cb
        self.add_item(tz_select)

    async def tz_cb(self, interaction: discord.Interaction):
        selected_label = interaction.data["values"][0]
        iana_tz = TIMEZONE_CHOICES[selected_label]

        # Open Date/Time Picker Modal with 5-min interval minute choices
        modal = ScheduleDateTimeModal(
            self.bot,
            self.hub_view,
            self.selected_channels,
            selected_label,
            iana_tz,
            self.draft_payload
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=ButtonStyle.red, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        embed = await self.hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.hub_view)


class ScheduleDateTimeModal(Modal, title="Set Scheduled Date & Time"):
    date_str = TextInput(
        label="Date (YYYY-MM-DD)",
        placeholder="e.g. 2026-08-15",
        required=True,
        max_length=10
    )
    hour_str = TextInput(
        label="Hour (00-23 in 24-hour format)",
        placeholder="e.g. 14 for 2:00 PM",
        required=True,
        max_length=2
    )
    minute_str = TextInput(
        label="Minute (00, 05, 10, 15, 20, 25, 30, 35...)",
        placeholder="e.g. 00, 05, 15, 30, 45",
        required=True,
        max_length=2
    )

    def __init__(self, bot, hub_view, selected_channels, tz_label, iana_tz, draft_payload=None):
        super().__init__()
        self.bot = bot
        self.hub_view = hub_view
        self.selected_channels = selected_channels
        self.tz_label = tz_label
        self.iana_tz = iana_tz
        self.draft_payload = draft_payload

        # Pre-fill with current local date/time + next 5 min interval
        tz = zoneinfo.ZoneInfo(iana_tz)
        now_local = datetime.datetime.now(tz)
        self.date_str.default = now_local.strftime("%Y-%m-%d")
        self.hour_str.default = now_local.strftime("%H")
        
        # Round up to nearest 5 min
        next_min = ((now_local.minute // 5) + 1) * 5
        if next_min >= 60:
            next_min = 0
        self.minute_str.default = f"{next_min:02d}"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d_val = self.date_str.value.strip()
            h_val = int(self.hour_str.value.strip())
            m_val = int(self.minute_str.value.strip())

            # Validate 5-minute interval constraint
            if m_val % 5 != 0 or m_val < 0 or m_val > 55:
                await interaction.response.send_message(
                    embed=embed_builder.error_embed(
                        "Invalid Minutes",
                        "Minutes must be in 5-minute intervals: 00, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55."
                    ),
                    ephemeral=True
                )
                return

            if h_val < 0 or h_val > 23:
                await interaction.response.send_message(
                    embed=embed_builder.error_embed("Invalid Hour", "Hour must be between 00 and 23."),
                    ephemeral=True
                )
                return

            date_parts = [int(p) for p in d_val.split("-")]
            if len(date_parts) != 3:
                raise ValueError("Date format error")

            tz = zoneinfo.ZoneInfo(self.iana_tz)
            dt_local = datetime.datetime(date_parts[0], date_parts[1], date_parts[2], h_val, m_val, tzinfo=tz)
            dt_utc = dt_local.astimezone(datetime.timezone.utc)

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if dt_utc <= now_utc:
                await interaction.response.send_message(
                    embed=embed_builder.warning_embed(
                        "Time in Past",
                        f"The scheduled time `{dt_local.strftime('%Y-%m-%d %H:%M')}` ({self.tz_label}) is in the past! Please choose a future time."
                    ),
                    ephemeral=True
                )
                return

            # Prepare payload
            payload = self.draft_payload or {
                "content": "📢 **Scheduled Community Announcement**",
                "embeds": [
                    {
                        "title": "Scheduled Broadcast",
                        "description": "This is a scheduled message broadcast.",
                        "color": embed_builder.COLOR_BRAND,
                        "fields": []
                    }
                ]
            }

            # Save to SQLite
            scheduled_id = await save_scheduled_message(
                self.bot,
                interaction.guild.id,
                interaction.user.id,
                self.selected_channels,
                payload,
                dt_utc.isoformat(),
                self.tz_label
            )

            ch_str = ", ".join([f"<#{cid}>" for cid in self.selected_channels])
            local_formatted = dt_local.strftime("%B %d, %Y at %I:%M %p")

            success_embed = embed_builder.success_embed(
                "Message Scheduled Successfully! 🎉",
                f"**Schedule ID:** `#{scheduled_id}`\n\n"
                f"📅 **Scheduled Time:** {local_formatted} ({self.tz_label})\n"
                f"🌍 **UTC Time:** {dt_utc.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"📢 **Target Channels:** {ch_str}\n\n"
                "The message will be automatically published at the scheduled time."
            )

            hub_embed = await self.hub_view.build_hub_embed(interaction.guild)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=success_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as err:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Scheduling Error", f"Failed to parse date/time: {str(err)}"),
                ephemeral=True
            )


# Edit View for an existing Scheduled Message

class ScheduleEditView(SecuredView):
    def __init__(self, bot, message_id: int, hub_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.message_id = message_id
        self.hub_view = hub_view

    async def get_item(self) -> Optional[Dict]:
        rows = await self.bot.database.fetchall(
            "SELECT * FROM scheduled_messages WHERE id = ?",
            (self.message_id,)
        )
        return dict(rows[0]) if rows else None

    async def build_embed(self, guild: discord.Guild) -> discord.Embed:
        item = await self.get_item()
        if not item:
            return embed_builder.error_embed("Error", "Scheduled message not found.")

        dt_utc = datetime.datetime.fromisoformat(item["scheduled_time"])
        ch_ids = json.loads(item["channel_ids"])
        ch_mentions = ", ".join([f"<#{cid}>" for cid in ch_ids])

        embed = embed_builder.base_embed(
            title=f"Edit Scheduled Message #{self.message_id}",
            description=f"Status: **{item['status'].upper()}**",
            color=embed_builder.COLOR_BRAND
        )
        embed.add_field(name="Scheduled Time", value=f"{dt_utc.strftime('%Y-%m-%d %H:%M UTC')} ({item['timezone_name']})", inline=True)
        embed.add_field(name="Target Channels", value=ch_mentions, inline=True)
        return embed

    @discord.ui.button(label="📢 Change Channels", style=ButtonStyle.blurple, row=0)
    async def edit_channels_btn(self, interaction: discord.Interaction, button: Button):
        ch_select_view = SecuredView(timeout=180)
        c_select = ChannelSelect(
            placeholder="Select new target channels (up to 5)...",
            min_values=1,
            max_values=5,
            channel_types=[ChannelType.text, ChannelType.news]
        )

        async def c_cb(inter: discord.Interaction):
            new_cids = [c.id for c in c_select.values]
            await update_scheduled_message_channels(self.bot, self.message_id, new_cids)
            embed = await self.build_embed(inter.guild)
            await inter.response.edit_message(embed=embed, view=self)

        c_select.callback = c_cb
        ch_select_view.add_item(c_select)

        await interaction.response.edit_message(
            embed=embed_builder.info_embed("Change Channels", "Select new channels for this schedule:"),
            view=ch_select_view
        )

    @discord.ui.button(label="❌ Cancel Schedule", style=ButtonStyle.red, row=0)
    async def cancel_schedule_btn(self, interaction: discord.Interaction, button: Button):
        await cancel_scheduled_message(self.bot, self.message_id)
        embed = await self.hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(
            embed=embed_builder.warning_embed("Schedule Cancelled", f"Scheduled message #{self.message_id} was cancelled."),
            view=self.hub_view
        )

    @discord.ui.button(label="⬅ Back to Hub", style=ButtonStyle.grey, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: Button):
        embed = await self.hub_view.build_hub_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.hub_view)


# Cog & Background Scheduler Loop

class ScheduledMessagesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduler_loop.start()

    def cog_unload(self):
        self.scheduler_loop.cancel()

    @tasks.loop(seconds=30)
    async def scheduler_loop(self):
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            pending = await self.bot.database.fetchall(
                "SELECT * FROM scheduled_messages WHERE status = 'pending' AND scheduled_time <= ?",
                (now_utc,)
            )
            for item in pending:
                item_dict = dict(item)
                await self.dispatch_scheduled_message(item_dict)
        except Exception as e:
            print(f"[Scheduled Messages] Error in scheduler loop: {e}")

    @scheduler_loop.before_loop
    async def before_scheduler(self):
        await self.bot.wait_until_ready()

    async def dispatch_scheduled_message(self, item: Dict):
        msg_id = item["id"]
        guild_id = item["guild_id"]
        channel_ids = json.loads(item["channel_ids"])
        payload = json.loads(item["payload"])

        guild = self.bot.get_guild(guild_id)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except Exception:
                pass

        if not guild:
            print(f"[Scheduled Messages] Guild {guild_id} not found for item #{msg_id}")
            await self.bot.database.execute(
                "UPDATE scheduled_messages SET status = 'failed' WHERE id = ?", (msg_id,)
            )
            return

        embed_script = EmbedScript.from_dict(payload)
        discord_embeds = embed_script.build_discord_embeds()
        content = payload.get("content") or None

        success_count = 0
        for cid in channel_ids:
            channel = guild.get_channel(cid)
            if not channel:
                try:
                    channel = await guild.fetch_channel(cid)
                except Exception:
                    pass

            if channel:
                try:
                    await channel.send(content=content, embeds=discord_embeds)
                    success_count += 1
                    print(f"[Scheduled Messages] Successfully sent scheduled message #{msg_id} to #{channel.name}")
                except Exception as send_err:
                    print(f"[Scheduled Messages] Failed to send #{msg_id} to channel {cid}: {send_err}")

        new_status = "sent" if success_count > 0 else "failed"
        await self.bot.database.execute(
            """
            UPDATE scheduled_messages
            SET status = ?, sent_at = datetime('now')
            WHERE id = ?
            """,
            (new_status, msg_id)
        )

async def setup(bot):
    await bot.add_cog(ScheduledMessagesCog(bot))
