"""
True Classic Bot - Quick Announcement Module
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc

Provides a streamlined, fast-navigation announcement creator with @everyone pinging,
multi-channel targeting, default banner thumbnail, instant dispatching, and timezone-aware
5-minute interval scheduling.
"""

import datetime
import json
import zoneinfo
from typing import List, Dict, Optional
import discord
from discord.ui import Button, View, Select, Modal, TextInput, ChannelSelect
from discord import TextStyle, ButtonStyle, ChannelType

import config
from utils import embed_builder
from modules.scheduled_messages import save_scheduled_message, TIMEZONE_CHOICES, MINUTE_INTERVALS

DEFAULT_BANNER_IMAGE = (
    "https://media.discordapp.net/attachments/1521574949238603906/1524101516611555379/"
    "Banner_Image-1.jpg?ex=6a6c2f65&is=6a6adde5&hm=e5d4a98c5fa7d8e2ffd9923503dd69c04ce3692a"
    "9bd1bb8d7485b1b3e0ec0582&=&format=webp&width=1536&height=864"
)

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
                    "You do not have required permissions to use Quick Announcement."
                ),
                ephemeral=True
            )
            return False
        return True


class QuickAnnouncementState:
    def __init__(self):
        self.title: str = "📢 Important Announcement"
        self.description: str = "Write announcement details here..."
        self.ping_tag: str = "@everyone"
        self.image_url: str = DEFAULT_BANNER_IMAGE
        self.color: int = embed_builder.COLOR_BRAND
        self.target_channel_ids: List[int] = []

    def build_announcement_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.title if self.title else "📢 Quick Announcement",
            description=self.description if self.description else "*(No description provided)*",
            color=self.color
        )
        if self.image_url:
            embed.set_image(url=self.image_url)
        embed.set_footer(text="True Classic Announcements")
        return embed

    def to_payload_dict(self, user_id: int) -> Dict:
        return {
            "user_id": user_id,
            "content": self.ping_tag if self.ping_tag != "None" else None,
            "embeds": [
                {
                    "title": self.title,
                    "description": self.description,
                    "color": self.color,
                    "image_url": self.image_url,
                    "footer_text": "True Classic Announcements",
                    "fields": []
                }
            ],
            "buttons": []
        }


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class EditAnnouncementModal(Modal, title="Edit Quick Announcement"):
    def __init__(self, state: QuickAnnouncementState, hub_view: "QuickAnnouncementHubView"):
        super().__init__()
        self.state = state
        self.hub_view = hub_view

        self.title_input = TextInput(
            label="Announcement Title",
            default=self.state.title,
            max_length=256,
            required=True
        )
        self.desc_input = TextInput(
            label="Announcement Description / Body",
            style=TextStyle.paragraph,
            default=self.state.description,
            max_length=4000,
            required=True
        )
        self.ping_input = TextInput(
            label="Ping Mention Tag (@everyone, @here, or None)",
            default=self.state.ping_tag,
            max_length=50,
            required=False
        )

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.ping_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.state.title = self.title_input.value.strip()
        self.state.description = self.desc_input.value.strip()
        ping_val = self.ping_input.value.strip()
        self.state.ping_tag = ping_val if ping_val else "None"

        await self.hub_view.update_hub(interaction)


class SetImageModal(Modal, title="Set Image / Banner URL"):
    def __init__(self, state: QuickAnnouncementState, hub_view: "QuickAnnouncementHubView"):
        super().__init__()
        self.state = state
        self.hub_view = hub_view

        self.image_input = TextInput(
            label="Image / Banner URL",
            default=self.state.image_url,
            max_length=1000,
            required=False,
            placeholder="Paste image URL here or leave blank to clear"
        )
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.image_input.value.strip()
        self.state.image_url = url if url else None
        await self.hub_view.update_hub(interaction)


# ---------------------------------------------------------------------------
# Quick Announcement Main Hub View
# ---------------------------------------------------------------------------

class QuickAnnouncementHubView(SecuredView):
    def __init__(self, bot, parent_panel_view=None, state: Optional[QuickAnnouncementState] = None):
        super().__init__(timeout=600)
        self.bot = bot
        self.parent_panel_view = parent_panel_view
        self.state = state or QuickAnnouncementState()

        # Add channel selector dynamically
        c_select = ChannelSelect(
            placeholder="Select target text channels (up to 10)...",
            min_values=1,
            max_values=10,
            channel_types=[ChannelType.text, ChannelType.news],
            row=0
        )
        c_select.callback = self.channel_select_cb
        self.add_item(c_select)

    async def channel_select_cb(self, interaction: discord.Interaction):
        self.state.target_channel_ids = [int(val) for val in interaction.data["values"]]
        await self.update_hub(interaction)

    def build_summary_embed(self, guild: Optional[discord.Guild]) -> discord.Embed:
        channels_str = (
            ", ".join([f"<#{cid}>" for cid in self.state.target_channel_ids])
            if self.state.target_channel_ids
            else "*No channels selected yet (use dropdown above)*"
        )

        ping_str = f"`{self.state.ping_tag}`" if self.state.ping_tag != "None" else "*No ping*"
        img_str = f"[View Image]({self.state.image_url})" if self.state.image_url else "*No image set*"

        embed = embed_builder.base_embed(
            title="⚡ Quick Announcement Hub",
            description=(
                f"Compose an announcement, target multiple channels, ping `@everyone`, and send instantly "
                f"or schedule for later.\n\n"
                f"📌 **Target Channels**: {channels_str}\n"
                f"🔔 **Mention Tag**: {ping_str}\n"
                f"🖼️ **Banner Image**: {img_str}\n\n"
                f"👇 **Live Embed Preview Below**"
            ),
            color=embed_builder.COLOR_BRAND
        )
        return embed

    async def update_hub(self, interaction: discord.Interaction):
        summary_embed = self.build_summary_embed(interaction.guild)
        preview_embed = self.state.build_announcement_embed()

        if interaction.response.is_done():
            await interaction.message.edit(embeds=[summary_embed, preview_embed], view=self)
        else:
            await interaction.response.edit_message(embeds=[summary_embed, preview_embed], view=self)

    # -- Buttons -----------------------------------------------------------

    @discord.ui.button(label="📝 Edit Content", style=ButtonStyle.blurple, row=1)
    async def edit_content_btn(self, interaction: discord.Interaction, button: Button):
        modal = EditAnnouncementModal(self.state, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🖼️ Banner Image", style=ButtonStyle.secondary, row=1)
    async def set_image_btn(self, interaction: discord.Interaction, button: Button):
        modal = SetImageModal(self.state, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔄 Reset Banner", style=ButtonStyle.grey, row=1)
    async def reset_image_btn(self, interaction: discord.Interaction, button: Button):
        self.state.image_url = DEFAULT_BANNER_IMAGE
        await self.update_hub(interaction)

    @discord.ui.button(label="🚀 Send Now", style=ButtonStyle.danger, row=2)
    async def send_now_btn(self, interaction: discord.Interaction, button: Button):
        if not self.state.target_channel_ids:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("No Channels Selected", "Please select at least one target text channel before sending."),
                ephemeral=True
            )
            return

        confirm_view = SendConfirmView(self.bot, self.state, self)
        ch_mentions = ", ".join([f"<#{cid}>" for cid in self.state.target_channel_ids])
        ping_text = f" and ping **{self.state.ping_tag}**" if self.state.ping_tag != "None" else ""

        embed = embed_builder.warning_embed(
            "⚠️ Confirm Announcement Dispatch",
            f"Are you sure you want to broadcast this announcement now to **{len(self.state.target_channel_ids)}** channel(s){ping_text}?\n\n"
            f"Target Channels: {ch_mentions}"
        )
        await interaction.response.edit_message(embeds=[embed], view=confirm_view)

    @discord.ui.button(label="⏰ Schedule for Later", style=ButtonStyle.success, row=2)
    async def schedule_btn(self, interaction: discord.Interaction, button: Button):
        if not self.state.target_channel_ids:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("No Channels Selected", "Please select at least one target text channel before scheduling."),
                ephemeral=True
            )
            return

        tz_view = AnnouncementScheduleTimezoneView(self.bot, self.state, self)
        embed = embed_builder.info_embed(
            "📅 Schedule Announcement (Step 1/2)",
            f"Target Channels: {', '.join([f'<#{cid}>' for cid in self.state.target_channel_ids])}\n"
            f"Ping Mention: `{self.state.ping_tag}`\n\n"
            f"Select your local Timezone for scheduling:"
        )
        await interaction.response.edit_message(embeds=[embed], view=tz_view)

    @discord.ui.button(label="⬅ Back to Mod Panel", style=ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: Button):
        if self.parent_panel_view:
            await self.parent_panel_view.show_panel(interaction)
        else:
            await interaction.response.send_message("Hub closed.", ephemeral=True)


# ---------------------------------------------------------------------------
# Send Confirmation View
# ---------------------------------------------------------------------------

class SendConfirmView(SecuredView):
    def __init__(self, bot, state: QuickAnnouncementState, hub_view: QuickAnnouncementHubView):
        super().__init__(timeout=180)
        self.bot = bot
        self.state = state
        self.hub_view = hub_view

    @discord.ui.button(label="✅ Confirm & Send Now", style=ButtonStyle.danger, row=0)
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        guild = interaction.guild
        embed = self.state.build_announcement_embed()
        ping_content = self.state.ping_tag if self.state.ping_tag != "None" else None

        sent_channels = []
        failed_channels = []

        for cid in self.state.target_channel_ids:
            channel = guild.get_channel(cid)
            if not channel:
                try:
                    channel = await guild.fetch_channel(cid)
                except Exception:
                    pass

            if channel:
                try:
                    await channel.send(content=ping_content, embed=embed)
                    sent_channels.append(channel.mention)
                except Exception as e:
                    failed_channels.append(f"<#{cid}> ({str(e)})")
            else:
                failed_channels.append(f"<#{cid}> (Channel not found)")

        result_lines = []
        if sent_channels:
            result_lines.append(f"✅ **Sent to ({len(sent_channels)})**: {', '.join(sent_channels)}")
        if failed_channels:
            result_lines.append(f"❌ **Failed ({len(failed_channels)})**: {', '.join(failed_channels)}")

        result_embed = embed_builder.success_embed(
            "🚀 Announcement Broadcast Complete",
            "\n\n".join(result_lines)
        )
        await interaction.message.edit(embeds=[result_embed], view=None)

    @discord.ui.button(label="❌ Cancel", style=ButtonStyle.secondary, row=0)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        await self.hub_view.update_hub(interaction)


# ---------------------------------------------------------------------------
# Scheduling Views (Timezone & 5-Min Step Picker)
# ---------------------------------------------------------------------------

class AnnouncementScheduleTimezoneView(SecuredView):
    def __init__(self, bot, state: QuickAnnouncementState, hub_view: QuickAnnouncementHubView):
        super().__init__(timeout=300)
        self.bot = bot
        self.state = state
        self.hub_view = hub_view

        options = []
        for label in TIMEZONE_CHOICES.keys():
            options.append(discord.SelectOption(label=label, value=label))

        tz_select = Select(placeholder="Select Timezone...", options=options, min_values=1, max_values=1)
        tz_select.callback = self.tz_cb
        self.add_item(tz_select)

    async def tz_cb(self, interaction: discord.Interaction):
        selected_tz_label = interaction.data["values"][0]
        iana_tz = TIMEZONE_CHOICES.get(selected_tz_label, "UTC")

        modal = AnnouncementTimePickerModal(self.bot, self.state, self.hub_view, selected_tz_label, iana_tz)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=ButtonStyle.red, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        await self.hub_view.update_hub(interaction)


def _get_timezone_obj(iana_tz: str) -> datetime.tzinfo:
    try:
        return zoneinfo.ZoneInfo(iana_tz)
    except Exception:
        return datetime.timezone.utc


class AnnouncementTimePickerModal(Modal, title="Schedule Time (5-Min Step Interval)"):
    def __init__(self, bot, state: QuickAnnouncementState, hub_view: QuickAnnouncementHubView, tz_label: str, iana_tz: str):
        super().__init__()
        self.bot = bot
        self.state = state
        self.hub_view = hub_view
        self.tz_label = tz_label
        self.iana_tz = iana_tz

        tz_obj = _get_timezone_obj(iana_tz)
        now_tz = datetime.datetime.now(tz_obj)
        # Round up to next 5 minutes
        rem = 5 - (now_tz.minute % 5)
        default_dt = now_tz + datetime.timedelta(minutes=rem)

        self.date_input = TextInput(
            label="Date (YYYY-MM-DD)",
            default=default_dt.strftime("%Y-%m-%d"),
            max_length=10,
            required=True
        )
        self.hour_input = TextInput(
            label="Hour (00 - 23)",
            default=default_dt.strftime("%H"),
            max_length=2,
            required=True
        )
        self.minute_input = TextInput(
            label="Minute (00, 05, 10, 15 ... 55)",
            default=default_dt.strftime("%M"),
            max_length=2,
            required=True
        )

        self.add_item(self.date_input)
        self.add_item(self.hour_input)
        self.add_item(self.minute_input)

    async def on_submit(self, interaction: discord.Interaction):
        date_str = self.date_input.value.strip()
        hour_str = self.hour_input.value.strip().zfill(2)
        min_str = self.minute_input.value.strip().zfill(2)

        # Ensure 5 minute interval alignment
        try:
            min_int = int(min_str)
            min_rounded = round(min_int / 5) * 5
            if min_rounded == 60:
                min_rounded = 55
            min_str = f"{min_rounded:02d}"
        except ValueError:
            await interaction.response.send_message("Invalid minute entered. Please enter a valid number.", ephemeral=True)
            return

        try:
            dt_naive = datetime.datetime.strptime(f"{date_str} {hour_str}:{min_str}", "%Y-%m-%d %H:%M")
            tz_obj = _get_timezone_obj(self.iana_tz)
            dt_local = dt_naive.replace(tzinfo=tz_obj)
            dt_utc = dt_local.astimezone(datetime.timezone.utc)
        except Exception as e:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Invalid Date/Time", f"Formatting error: {e}. Use format YYYY-MM-DD for date, 00-23 for hour, 00-55 for minute."),
                ephemeral=True
            )
            return

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if dt_utc <= now_utc:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Invalid Time", "Scheduled time must be in the future."),
                ephemeral=True
            )
            return

        scheduled_utc_iso = dt_utc.isoformat()
        payload = self.state.to_payload_dict(interaction.user.id)

        try:
            msg_id = await save_scheduled_message(
                bot=self.bot,
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                channel_ids=self.state.target_channel_ids,
                payload=payload,
                scheduled_utc_iso=scheduled_utc_iso,
                timezone_label=self.tz_label
            )

            ch_mentions = ", ".join([f"<#{cid}>" for cid in self.state.target_channel_ids])
            readable_local = dt_local.strftime("%Y-%m-%d %I:%M %p")

            success_embed = embed_builder.success_embed(
                "📅 Announcement Scheduled!",
                f"**Schedule ID**: `#{msg_id}`\n"
                f"**Channels**: {ch_mentions}\n"
                f"**Scheduled Time**: `{readable_local}` ({self.tz_label})\n"
                f"**UTC Timestamp**: `<t:{int(dt_utc.timestamp())}:F>` (<t:{int(dt_utc.timestamp())}:R>)\n"
                f"**Ping Tag**: `{self.state.ping_tag}`"
            )
            await interaction.response.edit_message(embeds=[success_embed], view=None)

        except Exception as err:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Database Error", f"Failed to save scheduled announcement: {err}"),
                ephemeral=True
            )
