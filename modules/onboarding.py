"""
True Classic Bot - Member Onboarding Module
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc
"""

import asyncio
import datetime
import discord
from discord.ui import Button, View, Select, Modal, TextInput, ChannelSelect
from discord import TextStyle, ButtonStyle, ChannelType
import config
from utils import embed_builder

ONBOARDING_CHANNEL_MENTION = f"<#{config.ONBOARDING_CHANNEL_ID}>" if config.ONBOARDING_CHANNEL_ID else "#onboarding"
INTRODUCTIONS_CHANNEL_MENTION = f"<#{config.INTRODUCTIONS_CHANNEL_ID}>" if config.INTRODUCTIONS_CHANNEL_ID else "#introductions"

DEFAULT_MESSAGE = (
    "👋 **Please give a warm welcome to our newest members!**\n\n"
    "Welcome to our affiliate community — we're thrilled to have you here! 🎉\n\n"
    f"**◈  Start here →** {ONBOARDING_CHANNEL_MENTION}\n"
    "Everything you need to hit the ground running lives there — guides, key resources, "
    "and all the essentials.\n\n"
    f"**◈  Say hello →** {INTRODUCTIONS_CHANNEL_MENTION}\n"
    "Pop in to introduce yourself! Tell us a little about you, drop your social media "
    "handles, and share your @s so the community can connect with you. 💚"
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
                    "You do not have the required permissions to use this control panel."
                ),
                ephemeral=True
            )
            return False
        return True

def _build_welcome_dm(member: discord.Member) -> discord.Embed:
    guild = member.guild
    onboarding_url = f"https://discord.com/channels/{guild.id}/{config.ONBOARDING_CHANNEL_ID}" if config.ONBOARDING_CHANNEL_ID else f"https://discord.com/channels/{guild.id}"
    intros_url = f"https://discord.com/channels/{guild.id}/{config.INTRODUCTIONS_CHANNEL_ID}" if config.INTRODUCTIONS_CHANNEL_ID else f"https://discord.com/channels/{guild.id}"

    embed = embed_builder.base_embed(
        title="👋  Welcome to the Community!",
        description=(
            f"Hi {member.mention}, we're so glad you're here! 🎉\n\n"
            f"You've just joined **{guild.name}**, and we want "
            "to make sure you have the smoothest possible start.\n\n"
            f"**◈  Start here →** [Open the #onboarding channel]({onboarding_url})\n"
            "That's your one-stop hub — guides, key resources, and answers to the most "
            "common questions all live there.\n\n"
            f"**◈  Introduce yourself →** [Head to #introductions]({intros_url})\n"
            "Don't be shy — say hello, tell us a bit about yourself, and feel free to "
            "share your social media handles and @s so the community can connect with you.\n\n"
            "Our team is always just a message away. Welcome aboard! 💚"
        ),
        color=embed_builder.COLOR_BRAND,
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed

async def _dm_welcome(members: list[discord.Member]) -> tuple[int, int]:
    success, fail = 0, 0
    for m in members:
        try:
            await m.send(embed=_build_welcome_dm(m))
            success += 1
            await asyncio.sleep(1)  # Rate limit protection
        except Exception as e:
            print(f"[Onboarding] Failed to send welcome DM to {m.display_name} ({m.id}): {e}")
            fail += 1
    return success, fail

async def _mark_onboarded(bot, guild_id: int, user_ids: list[int]):
    if not user_ids:
        return
    for uid in user_ids:
        await bot.database.execute(
            "INSERT OR IGNORE INTO onboarded_members (user_id, guild_id, onboarded_at) VALUES (?, ?, datetime('now'))",
            (uid, guild_id)
        )

class OnboardingHubView(SecuredView):
    def __init__(self, parent_panel_view, bot):
        super().__init__(timeout=300)
        self.parent_panel_view = parent_panel_view
        self.bot = bot

    @discord.ui.button(label="🔍 Scan for New Members", style=ButtonStyle.blurple)
    async def scan_members_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        print(f"[Onboarding] Scanning members for guild: {guild.name} ({guild.id})...")
        
        try:
            # Query DB for already onboarded members
            rows = await self.bot.database.fetchall(
                "SELECT user_id FROM onboarded_members WHERE guild_id = ?",
                (guild.id,)
            )
            onboarded_ids = {row["user_id"] for row in rows}

            # Fetch all members to get accurate join dates and roles
            members = []
            async for m in guild.fetch_members(limit=None):
                if not m.bot and m.id not in onboarded_ids:
                    members.append(m)
                    
            now = datetime.datetime.now(datetime.timezone.utc)
            recent_members = []
            
            for m in members:
                if m.joined_at:
                    delta = now - m.joined_at
                    if delta.days <= 30:
                        recent_members.append(m)
                        
            print(f"[Onboarding] Scan complete. Found {len(recent_members)} un-onboarded members joined in last 30 days.")
            
            if not recent_members:
                await interaction.followup.send(
                    embed=embed_builder.success_embed(
                        "Member Onboarding Hub",
                        "No un-onboarded new members found within the last 30 days. All set! 🎉"
                    ),
                    ephemeral=True
                )
                return

            # Group members into cohorts
            no_roles = [m for m in recent_members if len(m.roles) <= 1]
            joined_24h = [m for m in recent_members if (now - m.joined_at).total_seconds() < 86400]
            joined_7d = [m for m in recent_members if (now - m.joined_at).days < 7]
            joined_30d = recent_members
            
            cohorts = {
                "no_roles": {"name": "No Roles", "members": no_roles},
                "24h": {"name": "Joined < 24 Hours Ago", "members": joined_24h},
                "7d": {"name": "Joined < 7 Days Ago", "members": joined_7d},
                "30d": {"name": "All Un-onboarded (Last 30 Days)", "members": joined_30d}
            }
            
            scan_view = OnboardingScanResultView(cohorts, self.parent_panel_view, self.bot)
            
            embed = embed_builder.info_embed(
                "Member Onboarding Hub",
                f"Found **{len(recent_members)}** un-onboarded member(s) who joined in the last 30 days.\n\n"
                "Select a target group below to compose a welcome message."
            )
            
            await interaction.followup.send(embed=embed, view=scan_view, ephemeral=True)
            
        except Exception as e:
            print(f"[Onboarding] Error scanning members: {str(e)}")
            await interaction.followup.send(
                embed=embed_builder.error_embed("Scan Failed", f"Error scanning members: {str(e)}"),
                ephemeral=True
            )

    @discord.ui.button(label="⬅ Back to Panel", style=ButtonStyle.grey)
    async def back_to_panel(self, interaction: discord.Interaction, button: Button):
        await self.parent_panel_view.show_panel(interaction)


class OnboardingScanResultView(SecuredView):
    def __init__(self, cohorts, parent_panel_view, bot):
        super().__init__(timeout=300)
        self.cohorts = cohorts
        self.parent_panel_view = parent_panel_view
        self.bot = bot
        
        options = []
        for key, info in cohorts.items():
            count = len(info["members"])
            options.append(
                discord.SelectOption(
                    label=f"{info['name']} ({count} member{'s' if count != 1 else ''})",
                    value=key,
                    description=f"Select to onboard {count} member(s) in this group."
                )
            )
            
        select_cohort = Select(
            placeholder="Select a cohort to onboard...",
            options=options,
            min_values=1,
            max_values=1
        )
        select_cohort.callback = self.select_cohort_callback
        self.add_item(select_cohort)

    async def select_cohort_callback(self, interaction: discord.Interaction):
        key = interaction.data["values"][0]
        cohort_info = self.cohorts.get(key)
        
        if not cohort_info or not cohort_info["members"]:
            await interaction.response.send_message(
                embed=embed_builder.warning_embed("Empty Group", "No members in the selected group."),
                ephemeral=True
            )
            return
            
        modal = OnboardingComposerModal(cohort_info["name"], cohort_info["members"], self.parent_panel_view, self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="⬅ Back to Hub", style=ButtonStyle.grey, row=1)
    async def back_to_hub(self, interaction: discord.Interaction, button: Button):
        hub_view = OnboardingHubView(self.parent_panel_view, self.bot)
        await interaction.response.edit_message(
            embed=embed_builder.info_embed(
                "Member Onboarding Hub",
                "Scan for un-onboarded new members and send welcome messages."
            ),
            view=hub_view
        )


class OnboardingComposerModal(Modal, title="Compose Welcome Message"):
    message_text = TextInput(
        label="Public Channel Message",
        style=TextStyle.paragraph,
        placeholder="Enter your public welcome announcement message...",
        required=True,
        max_length=2000,
        default=DEFAULT_MESSAGE
    )

    def __init__(self, cohort_name, members, parent_panel_view, bot):
        super().__init__()
        self.cohort_name = cohort_name
        self.members = members
        self.parent_panel_view = parent_panel_view
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        composed_text = self.message_text.value
        
        delivery_view = OnboardingDeliveryView(
            self.cohort_name,
            self.members,
            composed_text,
            self.parent_panel_view,
            self.bot
        )
        
        embed = embed_builder.base_embed(
            title=f"Delivery Options • {self.cohort_name}",
            description=(
                f"Selected cohort: **{self.cohort_name}** ({len(self.members)} members)\n\n"
                "**Choose how to deliver the welcome:**\n"
                "1️⃣ **Post Publicly + Send Warm DM**: Tags members in a public text channel message AND sends a personalized welcome DM.\n"
                "2️⃣ **DM Welcome Only**: Sends the welcome DM directly without posting publicly."
            ),
            color=embed_builder.COLOR_BRAND
        )
        await interaction.response.send_message(embed=embed, view=delivery_view, ephemeral=True)


class OnboardingDeliveryView(SecuredView):
    def __init__(self, cohort_name, members, composed_text, parent_panel_view, bot):
        super().__init__(timeout=300)
        self.cohort_name = cohort_name
        self.members = members
        self.composed_text = composed_text
        self.parent_panel_view = parent_panel_view
        self.bot = bot

    @discord.ui.button(label="📢 Post Publicly + DM Welcome", style=ButtonStyle.green, row=0)
    async def post_and_dm_btn(self, interaction: discord.Interaction, button: Button):
        select_view = OnboardingChannelSelectView(
            self.cohort_name,
            self.members,
            self.composed_text,
            self.parent_panel_view,
            self.bot
        )
        embed = embed_builder.info_embed(
            "Select Target Text Channel",
            "Choose a channel below where the public welcome message will be posted with member mentions."
        )
        await interaction.response.edit_message(embed=embed, view=select_view)

    @discord.ui.button(label="✉️ DM Welcome Only", style=ButtonStyle.blurple, row=0)
    async def dm_only_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        success, fail = await _dm_welcome(self.members)
        await _mark_onboarded(self.bot, interaction.guild.id, [m.id for m in self.members])
        
        summary_embed = embed_builder.success_embed(
            "Onboarding Complete (DM Only)",
            f"**Cohort:** {self.cohort_name}\n"
            f"🟢 DMs Sent: **{success}**\n"
            f"🔴 Failed / DMs Closed: **{fail}**\n\n"
            "All target members have been marked as onboarded in SQLite database."
        )
        await interaction.followup.send(embed=summary_embed, ephemeral=True)


class OnboardingChannelSelectView(SecuredView):
    def __init__(self, cohort_name, members, composed_text, parent_panel_view, bot):
        super().__init__(timeout=300)
        self.cohort_name = cohort_name
        self.members = members
        self.composed_text = composed_text
        self.parent_panel_view = parent_panel_view
        self.bot = bot

        channel_select = ChannelSelect(
            placeholder="Pick text channel to post public welcome...",
            channel_types=[ChannelType.text, ChannelType.news],
            min_values=1,
            max_values=1
        )
        channel_select.callback = self.channel_selected_callback
        self.add_item(channel_select)

    async def channel_selected_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        channel_id = interaction.data["values"][0]
        channel = interaction.guild.get_channel(int(channel_id))
        
        if not channel:
            await interaction.followup.send(
                embed=embed_builder.error_embed("Channel Error", "Target channel not found."),
                ephemeral=True
            )
            return

        mentions_str = " ".join([m.mention for m in self.members])
        full_public_post = f"{mentions_str}\n\n{self.composed_text}"

        try:
            # 1. Post public message
            await channel.send(full_public_post)
            
            # 2. Send warm DMs
            success_dm, fail_dm = await _dm_welcome(self.members)
            
            # 3. Mark onboarded in SQLite DB
            await _mark_onboarded(self.bot, interaction.guild.id, [m.id for m in self.members])
            
            summary_embed = embed_builder.success_embed(
                "Onboarding Successful",
                f"Posted public welcome to {channel.mention}!\n\n"
                f"**DM Delivery Stats:**\n"
                f"🟢 Successfully DM'd: **{success_dm}**\n"
                f"🔴 DMs Closed / Failed: **{fail_dm}**\n\n"
                "All targeted members have been marked as onboarded."
            )
            await interaction.followup.send(embed=summary_embed, ephemeral=True)
            
        except Exception as e:
            print(f"[Onboarding] Public post failed: {e}")
            await interaction.followup.send(
                embed=embed_builder.error_embed("Post Failed", f"Could not post to {channel.mention}: {e}"),
                ephemeral=True
            )

class OnboardingCog(discord.ext.commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(OnboardingCog(bot))
