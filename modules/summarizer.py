"""
True Classic Bot - Inner Group Summarizer Module
Author: Aljay Leodones
Organization: True Classic

Mod Panel -> Summarizer -> pick group (Inner Circle / Academy) -> pick window
(Today / 7 Days / 1 Month) -> the bot scans every creator channel in that group and
publishes a triage report + full .txt breakdown to the reports channel.
"""

import datetime
import io
from typing import List, Optional

import discord
from discord.ext import commands
from discord.ui import Button, Select, View
from discord import ButtonStyle

import config
from utils import embed_builder
from core import inner_groups
from core import summarizer_engine as engine


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
                    "You do not have required permissions to run the Summarizer."
                ),
                ephemeral=True
            )
            return False
        return True


def _truncate_field(lines: List[str], limit: int = 1000) -> str:
    """Join lines without blowing the 1024-char embed field cap."""
    out, size = [], 0
    for line in lines:
        if size + len(line) + 1 > limit:
            out.append(f"…and {len(lines) - len(out)} more")
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out) if out else "—"


def build_summary_embed(scan: dict, requester: discord.abc.User) -> discord.Embed:
    """Channel-facing digest that sits above the attached .txt report."""
    group = scan["group"]
    tf = engine.TIMEFRAMES[scan["timeframe"]]
    t = scan["totals"]
    ordered = engine.sorted_results(scan["results"])
    now = scan["now"]

    needs_reply = t["buckets"]["P1"]
    follow_up = t["buckets"]["P2"]
    unreadable = t["buckets"]["XX"]

    if needs_reply:
        color = embed_builder.COLOR_ERROR
    elif follow_up:
        color = embed_builder.COLOR_WARNING
    else:
        color = embed_builder.COLOR_SUCCESS

    embed = embed_builder.base_embed(
        title=f"{group['emoji']} {group['label']} • Summary Report • {tf['label']}",
        description=(
            f"Scanned **{t['channels']}** creator channel(s) over **{tf['long'].lower()}**.\n"
            f"Full per-channel breakdown is in the attached text file."
        ),
        color=color
    )

    scoreboard = (
        "```ansi\n"
        f"[0;31m🔴 Needs reply now  {t['buckets']['P1']:>3}[0m\n"
        f"[0;33m🟠 Follow-up        {t['buckets']['P2']:>3}[0m\n"
        f"[0;36m🟡 Monitor          {t['buckets']['P3']:>3}[0m\n"
        f"[0;32m🟢 No action        {t['buckets']['P4']:>3}[0m\n"
        f"[0;37m⚪ No activity      {t['buckets']['P5']:>3}[0m\n"
        + (f"[0;31m🚫 Unreadable       {unreadable:>3}[0m\n" if unreadable else "")
        + "```"
    )
    embed.add_field(name="🚦 Triage Scoreboard", value=scoreboard, inline=True)

    stats = (
        "```text\n"
        f"Messages     {t['messages']:>5}\n"
        f"  creators   {t['creator_msgs']:>5}\n"
        f"  staff      {t['staff_msgs']:>5}\n"
        f"Active chans {t['active']:>3}/{t['channels']}\n"
        f"Unanswered   {t['unreplied']:>5}\n"
        f"Open Qs      {t['open_questions']:>5}\n"
        f"New since    {t['new_messages']:>5}\n"
        "```"
    )
    embed.add_field(name="📊 Volume", value=stats, inline=True)

    urgent = [r for r in ordered if r["bucket"] in ("P1", "P2")]
    if urgent:
        lines = []
        for r in urgent[:10]:
            b = engine.BUCKETS[r["bucket"]]
            wait = f" • waiting **{r['waiting_human']}**" if r.get("waiting_human") else ""
            qs = f" • {len(r['open_questions'])} open Q" if r["open_questions"] else ""
            lines.append(f"{b['emoji']} <#{r['channel_id']}>{wait}{qs}")
        embed.add_field(
            name=f"⏰ Action Queue ({len(urgent)} channel(s) need a mod)",
            value=_truncate_field(lines),
            inline=False
        )
    else:
        embed.add_field(
            name="⏰ Action Queue",
            value="✅ **Inbox zero.** No creator is waiting on a reply in this window.",
            inline=False
        )

    top_step_lines = []
    for r in ordered:
        if r["bucket"] not in ("P1", "P2") or not r["next_steps"]:
            continue
        top_step_lines.append(f"**#{r['channel_name']}** — {r['next_steps'][0]}")
        if len(top_step_lines) >= 5:
            break
    if top_step_lines:
        embed.add_field(name="✅ Do These First", value=_truncate_field(top_step_lines), inline=False)

    topic_totals = {}
    for r in scan["results"]:
        for name, emoji, hits in r["topics"]:
            entry = topic_totals.setdefault(name, {"emoji": emoji, "hits": 0, "channels": 0})
            entry["hits"] += hits
            entry["channels"] += 1
    if topic_totals:
        top_topics = sorted(topic_totals.items(), key=lambda kv: kv[1]["hits"], reverse=True)[:6]
        lines = [
            f"{v['emoji']} **{name}** — {v['hits']} msg across {v['channels']} channel(s)"
            for name, v in top_topics
        ]
        embed.add_field(name="🗂️ What The Group Is Talking About", value=_truncate_field(lines), inline=False)

    dormant = [r for r in ordered if r["bucket"] == "P5"]
    if dormant:
        embed.add_field(
            name=f"⚪ Silent In This Window ({len(dormant)})",
            value=_truncate_field([f"<#{r['channel_id']}>" for r in dormant], 900),
            inline=False
        )

    if unreadable:
        embed.add_field(
            name=f"🚫 Needs Fixing ({unreadable})",
            value=_truncate_field(
                [f"`#{r['channel_name']}` — {r['error']}" for r in ordered if r["bucket"] == "XX"]
            ),
            inline=False
        )

    embed.set_footer(
        text=(
            f"Requested by {requester.display_name} • {now.strftime('%Y-%m-%d %H:%M UTC')} • "
            "Open the .txt for conversation trails and per-channel next steps"
        )
    )
    return embed


def build_report_file(scan: dict, requester: discord.abc.User) -> discord.File:
    text = engine.build_report_text(scan, f"{requester.display_name} ({requester.id})")
    buf = io.BytesIO(text.encode("utf-8"))
    return discord.File(buf, filename=engine.report_filename(scan))


# ---------------------------------------------------------------------------
# Hub view
# ---------------------------------------------------------------------------

class GroupSelect(Select):
    def __init__(self, current: Optional[str]):
        options = []
        for key in inner_groups.all_group_keys():
            g = inner_groups.GROUPS[key]
            options.append(discord.SelectOption(
                label=g["label"],
                value=key,
                description=f"{len(g['channels'])} creator channel(s)",
                emoji=g["emoji"],
                default=(key == current),
            ))
        super().__init__(placeholder="Step 1 — choose a group…", options=options, min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.group_key = self.values[0]
        await self.view.refresh(interaction)


class TimeframeSelect(Select):
    def __init__(self, current: Optional[str]):
        options = []
        for key in ["today", "7d", "30d"]:
            tf = engine.TIMEFRAMES[key]
            options.append(discord.SelectOption(
                label=tf["long"],
                value=key,
                description=f"Scan messages from {tf['long'].lower()}",
                emoji=tf["emoji"],
                default=(key == current),
            ))
        super().__init__(placeholder="Step 2 — choose a window…", options=options, min_values=1, max_values=1, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.timeframe = self.values[0]
        await self.view.refresh(interaction)


class SummarizerHubView(SecuredView):
    def __init__(self, bot, parent_panel_view=None, group_key: Optional[str] = None, timeframe: str = "7d"):
        super().__init__(timeout=600)
        self.bot = bot
        self.parent_panel_view = parent_panel_view
        self.group_key = group_key
        self.timeframe = timeframe
        self.running = False
        self._build_items()

    def _build_items(self):
        self.clear_items()
        self.add_item(GroupSelect(self.group_key))
        self.add_item(TimeframeSelect(self.timeframe))

        ready = self.group_key is not None

        run_btn = Button(
            label="📤 Generate & Post Report",
            style=ButtonStyle.green if ready else ButtonStyle.secondary,
            disabled=not ready,
            row=2,
        )
        run_btn.callback = self.run_and_post
        self.add_item(run_btn)

        preview_btn = Button(
            label="👁️ Preview (only me)",
            style=ButtonStyle.blurple,
            disabled=not ready,
            row=2,
        )
        preview_btn.callback = self.run_preview
        self.add_item(preview_btn)

        history_btn = Button(label="🧾 Run History", style=ButtonStyle.grey, row=3)
        history_btn.callback = self.show_history
        self.add_item(history_btn)

        back_btn = Button(label="⬅ Back to Panel", style=ButtonStyle.grey, row=3)
        back_btn.callback = self.back_to_panel
        self.add_item(back_btn)

    def _report_channel(self, guild: discord.Guild):
        return guild.get_channel(config.SUMMARY_REPORT_CHANNEL_ID)

    async def build_hub_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = embed_builder.base_embed(
            title="🧠 Inner Group Summarizer",
            description=(
                "Scans every creator channel in a group, works out **who is waiting on us**, "
                "and posts a triage report plus a full `.txt` breakdown with next steps for each channel."
            ),
            color=embed_builder.COLOR_BRAND
        )

        if self.group_key:
            g = inner_groups.GROUPS[self.group_key]
            group_line = f"{g['emoji']} **{g['label']}** — {len(g['channels'])} channel(s)"
        else:
            group_line = "*not selected*"

        tf = engine.TIMEFRAMES[self.timeframe]
        report_channel = self._report_channel(guild)
        dest = report_channel.mention if report_channel else f"`{config.SUMMARY_REPORT_CHANNEL_ID}` ⚠️ *not found*"

        embed.add_field(
            name="⚙️ Current Selection",
            value=(
                f"**Group:** {group_line}\n"
                f"**Window:** {tf['emoji']} {tf['long']}\n"
                f"**Report goes to:** {dest}"
            ),
            inline=False
        )

        embed.add_field(
            name="🚦 How Channels Get Sorted",
            value=(
                "🔴 **Needs reply now** — creator spoke last and we never answered\n"
                "🟠 **Follow-up** — we spoke last, thread went quiet, or a blocker was raised\n"
                "🟡 **Monitor** — active and healthy, ball is in the creator's court\n"
                "🟢 **No action** — closed out\n"
                "⚪ **No activity** — nothing in the window"
            ),
            inline=False
        )

        embed.add_field(
            name="📋 What The Report Gives You",
            value=(
                "▸ **Triage board** — every channel ranked, longest wait first\n"
                "▸ **Mod worksheet** — a `[ ]` checklist you can paste into your notes\n"
                "▸ **Per channel** — topics discussed, quoted unanswered questions, "
                "conversation trail, and numbered next steps\n"
                "▸ **New since last report** — what moved since the previous run"
            ),
            inline=False
        )

        rows = await self.bot.database.fetchall(
            "SELECT * FROM summarizer_runs WHERE guild_id = ? ORDER BY id DESC LIMIT 3",
            (guild.id,)
        )
        if rows:
            lines = []
            for row in rows:
                g = inner_groups.GROUPS.get(row["group_key"], {"short": row["group_key"]})
                lines.append(
                    f"`#{row['id']}` {g['short']} • {row['timeframe']} • "
                    f"{row['created_at']} UTC • 🔴{row['needs_reply']} 🟠{row['follow_up']} ⚪{row['no_activity']}"
                )
            embed.add_field(name="🧾 Recent Runs", value="\n".join(lines), inline=False)

        if self.group_key:
            est = max(1, round(len(inner_groups.GROUPS[self.group_key]["channels"]) * 0.6))
            embed.set_footer(text=f"True Classic • Scan takes roughly {est}s — the bot will keep you posted")

        return embed

    async def refresh(self, interaction: discord.Interaction):
        self._build_items()
        embed = await self.build_hub_embed(interaction.guild)
        if interaction.response.is_done():
            # Already deferred/responded -> edit the hub message itself, not the followup.
            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id, embed=embed, view=self
                )
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    # -- actions ------------------------------------------------------------

    async def _run_scan(self, interaction: discord.Interaction) -> Optional[dict]:
        group = inner_groups.GROUPS[self.group_key]
        tf = engine.TIMEFRAMES[self.timeframe]

        status = await interaction.followup.send(
            embed=embed_builder.info_embed(
                "Scanning…",
                f"Reading **{len(group['channels'])}** {group['label']} channel(s) over {tf['long'].lower()}."
            ),
            ephemeral=True,
            wait=True
        )

        async def progress(done: int, total: int, current: str):
            filled = "█" * int((done / total) * 20)
            empty = "░" * (20 - len(filled))
            await status.edit(embed=embed_builder.info_embed(
                "Scanning…",
                f"`{filled}{empty}` **{done}/{total}**\nLast read: `{current}`"
            ))

        print(f"[Summarizer] {interaction.user} started {self.group_key}/{self.timeframe} scan")
        try:
            scan = await engine.scan_group(self.bot, interaction.guild, group, self.timeframe, progress)
        except Exception as exc:
            print(f"[Summarizer] Scan failed: {exc}")
            await status.edit(embed=embed_builder.error_embed("Scan Failed", f"```\n{exc}\n```"))
            return None

        await status.edit(embed=embed_builder.success_embed(
            "Scan Complete",
            f"Read **{scan['totals']['messages']}** message(s) across **{scan['totals']['channels']}** channel(s)."
        ))
        return scan

    async def run_and_post(self, interaction: discord.Interaction):
        """Button entry point: defer, scan, publish, then refresh the hub message."""
        if self.running:
            await interaction.response.send_message("A scan is already running — hold on.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.generate_and_post(interaction, refresh_hub=True)

    async def generate_and_post(self, interaction: discord.Interaction, refresh_hub: bool = False):
        """Assumes the interaction is already deferred (ephemeral)."""
        if self.running:
            await interaction.followup.send("A scan is already running — hold on.", ephemeral=True)
            return
        self.running = True
        try:
            scan = await self._run_scan(interaction)
            if scan is None:
                return

            report_channel = self._report_channel(interaction.guild)
            if report_channel is None:
                try:
                    report_channel = await self.bot.fetch_channel(config.SUMMARY_REPORT_CHANNEL_ID)
                except Exception:
                    report_channel = None

            if report_channel is None:
                await interaction.followup.send(
                    embed=embed_builder.error_embed(
                        "Report Channel Unreachable",
                        f"Could not resolve channel `{config.SUMMARY_REPORT_CHANNEL_ID}`. "
                        "Check the ID and that the bot can see it. Use **Preview** in the meantime."
                    ),
                    ephemeral=True
                )
                return

            embed = build_summary_embed(scan, interaction.user)
            file = build_report_file(scan, interaction.user)

            try:
                posted = await report_channel.send(embed=embed, file=file)
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=embed_builder.error_embed(
                        "Cannot Post Report",
                        f"Missing **Send Messages** / **Attach Files** in {report_channel.mention}."
                    ),
                    ephemeral=True
                )
                return

            await self._record_run(interaction, scan, report_channel.id, posted.id)

            t = scan["totals"]
            await interaction.followup.send(
                embed=embed_builder.success_embed(
                    "Report Published",
                    f"Posted to {report_channel.mention} → [jump to report]({posted.jump_url})\n\n"
                    f"🔴 **{t['buckets']['P1']}** need a reply now • "
                    f"🟠 **{t['buckets']['P2']}** need a follow-up • "
                    f"⚪ **{t['buckets']['P5']}** silent"
                ),
                ephemeral=True
            )
            if refresh_hub:
                await self.refresh(interaction)
        finally:
            self.running = False

    async def run_preview(self, interaction: discord.Interaction):
        if self.running:
            await interaction.response.send_message("A scan is already running — hold on.", ephemeral=True)
            return
        self.running = True
        await interaction.response.defer(ephemeral=True)
        try:
            scan = await self._run_scan(interaction)
            if scan is None:
                return
            await interaction.followup.send(
                content="**Preview only — this was not posted to the reports channel.**",
                embed=build_summary_embed(scan, interaction.user),
                file=build_report_file(scan, interaction.user),
                ephemeral=True
            )
        finally:
            self.running = False

    async def _record_run(self, interaction, scan: dict, channel_id: int, message_id: int):
        t = scan["totals"]
        await self.bot.database.execute(
            """
            INSERT INTO summarizer_runs
                (guild_id, group_key, timeframe, requested_by, channels_scanned, messages_scanned,
                 needs_reply, follow_up, no_activity, report_channel_id, report_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interaction.guild.id, scan["group"]["key"], scan["timeframe"], interaction.user.id,
                t["channels"], t["messages"], t["buckets"]["P1"], t["buckets"]["P2"], t["buckets"]["P5"],
                channel_id, message_id,
            )
        )

    async def show_history(self, interaction: discord.Interaction):
        rows = await self.bot.database.fetchall(
            "SELECT * FROM summarizer_runs WHERE guild_id = ? ORDER BY id DESC LIMIT 10",
            (interaction.guild.id,)
        )
        if not rows:
            await interaction.response.send_message(
                embed=embed_builder.info_embed("No Runs Yet", "No Summarizer report has been generated yet."),
                ephemeral=True
            )
            return

        lines = []
        for row in rows:
            g = inner_groups.GROUPS.get(row["group_key"], {"label": row["group_key"], "emoji": "•"})
            tf = engine.TIMEFRAMES.get(row["timeframe"], {"label": row["timeframe"]})
            link = ""
            if row["report_channel_id"] and row["report_message_id"]:
                link = (
                    f" • [report](https://discord.com/channels/"
                    f"{interaction.guild.id}/{row['report_channel_id']}/{row['report_message_id']})"
                )
            lines.append(
                f"`#{row['id']}` {g['emoji']} **{g.get('label')}** • {tf['label']} • {row['created_at']} UTC\n"
                f"　▸ {row['channels_scanned']} channels, {row['messages_scanned']} msgs • "
                f"🔴{row['needs_reply']} 🟠{row['follow_up']} ⚪{row['no_activity']} • <@{row['requested_by']}>{link}"
            )

        embed = embed_builder.info_embed("🧾 Summarizer Run History", "Last 10 generated reports.")
        embed.add_field(name="Runs", value=_truncate_field(lines, 1000), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def back_to_panel(self, interaction: discord.Interaction):
        if self.parent_panel_view:
            await self.parent_panel_view.show_panel(interaction)
        else:
            await interaction.response.send_message("Summarizer closed.", ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class SummarizerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="summarize",
        description="Generate a mod triage summary for the Inner Circle or Academy DM channels"
    )
    @discord.app_commands.describe(
        group="Which inner group to scan",
        window="How far back to scan"
    )
    @discord.app_commands.choices(
        group=[
            discord.app_commands.Choice(name="Inner Circle DM's", value="inner_circle"),
            discord.app_commands.Choice(name="Academy DM's", value="academy"),
        ],
        window=[
            discord.app_commands.Choice(name="Today", value="today"),
            discord.app_commands.Choice(name="Last 7 Days", value="7d"),
            discord.app_commands.Choice(name="Last 30 Days (1 Month)", value="30d"),
        ],
    )
    async def summarize(
        self,
        interaction: discord.Interaction,
        group: discord.app_commands.Choice[str],
        window: discord.app_commands.Choice[str],
    ):
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        if not has_role:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to run this command."),
                ephemeral=True
            )
            return

        view = SummarizerHubView(self.bot, None, group_key=group.value, timeframe=window.value)
        await interaction.response.defer(ephemeral=True)
        await view.generate_and_post(interaction, refresh_hub=False)

    @discord.app_commands.command(
        name="summarizer",
        description="Open the Inner Group Summarizer hub"
    )
    async def summarizer_hub(self, interaction: discord.Interaction):
        has_role = False
        if interaction.guild:
            user_roles = [role.id for role in interaction.user.roles]
            for role_id in config.AUTHORIZED_ROLES:
                if role_id in user_roles:
                    has_role = True
                    break
        if not has_role:
            await interaction.response.send_message(
                embed=embed_builder.error_embed("Permission Denied", "You do not have permission to run this command."),
                ephemeral=True
            )
            return

        view = SummarizerHubView(self.bot, None)
        embed = await view.build_hub_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SummarizerCog(bot))
