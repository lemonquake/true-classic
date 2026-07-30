"""
True Classic Bot - Member Report & Analytics Module
Author: Aljay Leodones
Organization: True Classic
Details: Prepared for True Classic - The features of this Bot are original and can't be found in any other 3rd-party bots like Mee6, Dyno, etc
"""

from collections import defaultdict
import datetime
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, ChannelSelect
from discord import ButtonStyle, ChannelType
import config
from utils import embed_builder

TIMEFRAME_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30
}

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
                embed=embed_builder.error_embed("Permission Denied", "You do not have required permissions."),
                ephemeral=True
            )
            return False
        return True

def _delta_line(label: str, current: int, previous: int | None) -> str:
    if previous is None:
        return f"{label:<10}│ {current:>5}   (no prior data)"

    delta = current - previous
    if delta > 0:
        arrow, sign = "📈", f"+{delta}"
    elif delta < 0:
        arrow, sign = "📉", f"{delta}"
    else:
        arrow, sign = "➖", "±0"

    pct = f" ({delta / previous * 100:+.1f}%)" if previous and previous > 0 else ""
    return f"{label:<10}│ {previous if previous is not None else 0:>5} → {current:<5} {arrow} {sign}{pct}"

async def record_snapshot(bot, guild: discord.Guild) -> dict:
    today_str = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    
    total = guild.member_count or len(guild.members)
    bots = len([m for m in guild.members if m.bot])
    humans = total - bots
    admins = len([m for m in guild.members if m.guild_permissions.administrator and not m.bot])
    online = len([m for m in guild.members if m.status != discord.Status.offline])
    
    await bot.database.execute(
        """
        INSERT INTO member_snapshots (guild_id, snapshot_date, total, humans, bots, online, admins)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, snapshot_date) DO UPDATE SET
            total = excluded.total,
            humans = excluded.humans,
            bots = excluded.bots,
            online = excluded.online,
            admins = excluded.admins
        """,
        (guild.id, today_str, total, humans, bots, online, admins)
    )
    return {
        "date": today_str,
        "total": total,
        "humans": humans,
        "bots": bots,
        "online": online,
        "admins": admins
    }

async def reconcile_joins_from_members(bot, guild: discord.Guild) -> int:
    counts = defaultdict(int)
    async for m in guild.fetch_members(limit=None):
        if m.bot or m.joined_at is None:
            continue
        day = m.joined_at.astimezone(datetime.timezone.utc).date().isoformat()
        counts[day] += 1

    for day, c in counts.items():
        await bot.database.execute(
            """
            INSERT INTO member_joins (guild_id, period, period_date, joins)
            VALUES (?, 'day', ?, ?)
            ON CONFLICT(guild_id, period, period_date)
            DO UPDATE SET joins = MAX(joins, excluded.joins)
            """,
            (guild.id, day, c)
        )
    return len(counts)

async def get_baseline_snapshot(bot, guild_id: int, days_ago: int) -> dict | None:
    target_date = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=days_ago)).isoformat()
    row = await bot.database.fetchone(
        "SELECT * FROM member_snapshots WHERE guild_id = ? AND snapshot_date = ?",
        (guild_id, target_date)
    )
    if not row:
        # Fetch closest available snapshot if exact date not available
        row = await bot.database.fetchone(
            "SELECT * FROM member_snapshots WHERE guild_id = ? ORDER BY ABS(JULIANDAY(snapshot_date) - JULIANDAY(?)) ASC LIMIT 1",
            (guild_id, target_date)
        )
    return dict(row) if row else None

async def get_join_history(bot, guild_id: int):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    
    rows = await bot.database.fetchall(
        "SELECT period_date, joins FROM member_joins WHERE guild_id = ? AND period = 'day' ORDER BY period_date DESC",
        (guild_id,)
    )
    joins_map = {row["period_date"]: row["joins"] for row in rows}

    joins_today = joins_map.get(today.isoformat(), 0)
    
    current_week_start = today - datetime.timedelta(days=today.weekday())
    joins_week = sum(joins_map.get((current_week_start + datetime.timedelta(days=i)).isoformat(), 0) for i in range(7))
    
    current_month_start = today.replace(day=1)
    joins_month = sum(count for d_str, count in joins_map.items() if d_str >= current_month_start.isoformat())
    
    # Last 7 days breakdown
    last_7_parts = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        count = joins_map.get(d.isoformat(), 0)
        last_7_parts.append(f"{d.day}:{count}")
    last_7_str = "  ".join(last_7_parts)

    return joins_today, joins_week, joins_month, last_7_str

async def compute_engagement_leaderboard(bot, guild: discord.Guild, days: int) -> list[tuple[str, int]]:
    since_date = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=days)).isoformat()
    rows = await bot.database.fetchall(
        """
        SELECT user_id, SUM(messages) as total_msgs
        FROM engagement_daily
        WHERE guild_id = ? AND day >= ?
        GROUP BY user_id
        ORDER BY total_msgs DESC
        LIMIT 5
        """,
        (guild.id, since_date)
    )
    leaderboard = []
    for row in rows:
        member = guild.get_member(row["user_id"])
        name = member.display_name if member else f"User {row['user_id']}"
        leaderboard.append((name, row["total_msgs"]))
    return leaderboard

async def create_report_embed(bot, guild: discord.Guild, timeframe: str = "daily") -> discord.Embed:
    days_ago = TIMEFRAME_DAYS.get(timeframe, 1)
    
    stats = await record_snapshot(bot, guild)
    baseline = await get_baseline_snapshot(bot, guild.id, days_ago)
    joins_today, joins_week, joins_month, last_7_str = await get_join_history(bot, guild.id)
    top_active = await compute_engagement_leaderboard(bot, guild, days_ago)

    timeframe_labels = {"daily": "Yesterday", "weekly": "7 Days Ago", "monthly": "30 Days Ago"}
    lbl = timeframe_labels.get(timeframe, "Prior Baseline")

    total_prev = baseline["total"] if baseline else None
    humans_prev = baseline["humans"] if baseline else None
    bots_prev = baseline["bots"] if baseline else None
    online_prev = baseline["online"] if baseline else None
    admins_prev = baseline["admins"] if baseline else None

    right_now_lines = [
        "```text",
        _delta_line("Total", stats["total"], total_prev),
        _delta_line("Members", stats["humans"], humans_prev),
        _delta_line("Bots", stats["bots"], bots_prev),
        _delta_line("Online", stats["online"], online_prev),
        _delta_line("Admins", stats["admins"], admins_prev),
        "```"
    ]
    right_now_value = "\n".join(right_now_lines)

    color = embed_builder.COLOR_SUCCESS if timeframe == "daily" else (
        embed_builder.COLOR_INFO if timeframe == "weekly" else 0x9B59B6
    )

    embed = embed_builder.base_embed(
        title=f"📊 Member Analytics • {timeframe.capitalize()} Report (vs {lbl})",
        description="Comprehensive public report on community growth, member baselines, and activity trends.",
        color=color
    )

    embed.add_field(name="👤 Membership Growth & Baselines", value=right_now_value, inline=False)

    joins_value = (
        f"**{joins_today}** today • **{joins_week}** this week • **{joins_month}** this month\n"
        f"```text\nLast 7 days │ {last_7_str}\n```"
    )
    embed.add_field(name="🆕 Join Velocity", value=joins_value, inline=False)

    if top_active:
        leaderboard_str = "\n".join([f"`#{i+1}` **{name}** — {msgs} msg(s)" for i, (name, msgs) in enumerate(top_active)])
        embed.add_field(name="🔥 Top Active Members", value=leaderboard_str, inline=False)

    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    embed.set_footer(text=f"{config.BOT_NAME if hasattr(config, 'BOT_NAME') else 'True Classic'} • Last updated: {now_str} UTC • Auto-refreshes every 3h")
    return embed

async def refresh_all_deployed_reports(bot):
    rows = await bot.database.fetchall("SELECT * FROM member_reports")
    success_count, fail_count = 0, 0
    
    for row in rows:
        guild = bot.get_guild(row["guild_id"])
        if not guild:
            try:
                guild = await bot.fetch_guild(row["guild_id"])
            except Exception:
                continue
                
        channel = guild.get_channel(row["channel_id"]) if guild else None
        if not channel and guild:
            try:
                channel = await guild.fetch_channel(row["channel_id"])
            except Exception:
                pass
                
        if not channel:
            await bot.database.execute("DELETE FROM member_reports WHERE guild_id = ? AND timeframe = ?", (row["guild_id"], row["timeframe"]))
            fail_count += 1
            continue

        try:
            embed = await create_report_embed(bot, guild, row["timeframe"])
            msg = await channel.fetch_message(row["message_id"])
            await msg.edit(embed=embed)
            await bot.database.execute(
                "UPDATE member_reports SET updated_at = datetime('now') WHERE guild_id = ? AND timeframe = ?",
                (row["guild_id"], row["timeframe"])
            )
            success_count += 1
        except Exception as e:
            print(f"[Member Report] Failed to update {row['timeframe']} report in #{channel.name}: {e}")
            if "Unknown Message" in str(e) or "10008" in str(e):
                await bot.database.execute("DELETE FROM member_reports WHERE guild_id = ? AND timeframe = ?", (row["guild_id"], row["timeframe"]))
                fail_count += 1

    return success_count, fail_count

class ReportChannelSelect(ChannelSelect):
    def __init__(self, label: str, timeframe: str, row: int):
        super().__init__(
            placeholder=f"{label} -> pick a channel",
            min_values=1,
            max_values=1,
            channel_types=[ChannelType.text, ChannelType.news],
            row=row,
            custom_id=f"report_select_{timeframe}"
        )
        self.timeframe = timeframe

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        channel_id = self.values[0].id
        channel = guild.get_channel(channel_id)
        
        if not channel:
            await interaction.followup.send(
                embed=embed_builder.error_embed("Error", "Could not resolve selected channel."),
                ephemeral=True
            )
            return

        bot = interaction.client
        
        # Check existing report deployment
        existing = await bot.database.fetchone(
            "SELECT * FROM member_reports WHERE guild_id = ? AND timeframe = ?",
            (guild.id, self.timeframe)
        )
        if existing:
            old_channel = guild.get_channel(existing["channel_id"])
            if old_channel:
                try:
                    old_msg = await old_channel.fetch_message(existing["message_id"])
                    await old_msg.delete()
                except Exception:
                    pass

        try:
            embed = await create_report_embed(bot, guild, self.timeframe)
            new_msg = await channel.send(embed=embed)
            
            await bot.database.execute(
                """
                INSERT INTO member_reports (guild_id, timeframe, channel_id, message_id, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(guild_id, timeframe) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    updated_at = datetime('now')
                """,
                (guild.id, self.timeframe, channel.id, new_msg.id)
            )
            
            await interaction.followup.send(
                embed=embed_builder.success_embed(
                    "Report Deployed",
                    f"Successfully published **{self.timeframe.capitalize()}** report to {channel.mention}."
                ),
                ephemeral=True
            )
            
            if hasattr(self.view, "get_hub_embed"):
                hub_embed = await self.view.get_hub_embed(guild)
                await interaction.message.edit(embed=hub_embed, view=self.view)
                
        except Exception as e:
            print(f"[Member Report] Error deploying report: {e}")
            await interaction.followup.send(
                embed=embed_builder.error_embed("Deployment Failed", str(e)),
                ephemeral=True
            )


class MemberReportHubView(SecuredView):
    def __init__(self, bot, parent_panel_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.parent_panel_view = parent_panel_view

        self.add_item(ReportChannelSelect(label="Post DAILY report", timeframe="daily", row=1))
        self.add_item(ReportChannelSelect(label="Post WEEKLY report", timeframe="weekly", row=2))
        self.add_item(ReportChannelSelect(label="Post MONTHLY report", timeframe="monthly", row=3))

    async def get_hub_embed(self, guild: discord.Guild) -> discord.Embed:
        await record_snapshot(self.bot, guild)
        await reconcile_joins_from_members(self.bot, guild)
        
        daily_embed = await create_report_embed(self.bot, guild, "daily")
        
        deployed_rows = await self.bot.database.fetchall(
            "SELECT * FROM member_reports WHERE guild_id = ?",
            (guild.id,)
        )
        deployed_dict = {row["timeframe"]: row for row in deployed_rows}

        status_lines = []
        for tf in ["daily", "weekly", "monthly"]:
            info = deployed_dict.get(tf)
            if info:
                ch = guild.get_channel(info["channel_id"])
                mention = ch.mention if ch else f"#{info['channel_id']}"
                status_lines.append(f"🟢 **{tf.capitalize()}**: Active in {mention}")
            else:
                status_lines.append(f"🔴 **{tf.capitalize()}**: Not Deployed")
                
        status_str = "\n".join(status_lines)

        embed = embed_builder.info_embed(
            "📊 Member Analytics & Growth Hub",
            "Manage self-updating growth reports and daily baseline snapshots for your server."
        )

        embed.add_field(name="👤 Current Growth Overview", value=daily_embed.fields[0].value, inline=False)
        embed.add_field(name="📋 Deployed Public Reports", value=f"{status_str}\n\n*Auto-refreshes every 3 hours.*", inline=False)
        return embed

    @discord.ui.button(label="Preview Daily", style=ButtonStyle.blurple, row=0)
    async def preview_daily_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        embed = await create_report_embed(self.bot, interaction.guild, "daily")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Preview Weekly", style=ButtonStyle.blurple, row=0)
    async def preview_weekly_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        embed = await create_report_embed(self.bot, interaction.guild, "weekly")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Preview Monthly", style=ButtonStyle.blurple, row=0)
    async def preview_monthly_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        embed = await create_report_embed(self.bot, interaction.guild, "monthly")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Refresh Now", style=ButtonStyle.green, row=4)
    async def refresh_now_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        await record_snapshot(self.bot, interaction.guild)
        await reconcile_joins_from_members(self.bot, interaction.guild)
        
        success, failed = await refresh_all_deployed_reports(self.bot)
        hub_embed = await self.get_hub_embed(interaction.guild)
        
        await interaction.followup.send(
            embed=embed_builder.success_embed("Reports Refreshed", f"Updated **{success}** live report(s). Removed **{failed}** broken report(s)."),
            ephemeral=True
        )
        await interaction.message.edit(embed=hub_embed, view=self)

    @discord.ui.button(label="Remove Reports", style=ButtonStyle.red, row=4)
    async def remove_reports_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        
        rows = await self.bot.database.fetchall(
            "SELECT * FROM member_reports WHERE guild_id = ?",
            (interaction.guild.id,)
        )
        deleted_count = 0
        for row in rows:
            ch = interaction.guild.get_channel(row["channel_id"])
            if ch:
                try:
                    msg = await ch.fetch_message(row["message_id"])
                    await msg.delete()
                    deleted_count += 1
                except Exception:
                    pass
                    
        await self.bot.database.execute("DELETE FROM member_reports WHERE guild_id = ?", (interaction.guild.id,))
        hub_embed = await self.get_hub_embed(interaction.guild)
        
        await interaction.followup.send(
            embed=embed_builder.warning_embed("Reports Removed", f"Deleted **{deleted_count}** public report message(s) and cleared deployment settings."),
            ephemeral=True
        )
        await interaction.message.edit(embed=hub_embed, view=self)

    @discord.ui.button(label="Back to Main Panel", style=ButtonStyle.grey, row=4)
    async def back_to_panel_btn(self, interaction: discord.Interaction, button: Button):
        await self.parent_panel_view.show_panel(interaction)


class MemberReportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_refresh_loop.start()

    def cog_unload(self):
        self.auto_refresh_loop.cancel()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        day = member.joined_at.astimezone(datetime.timezone.utc).date().isoformat() if member.joined_at else datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        await self.bot.database.execute(
            """
            INSERT INTO member_joins (guild_id, period, period_date, joins)
            VALUES (?, 'day', ?, 1)
            ON CONFLICT(guild_id, period, period_date)
            DO UPDATE SET joins = joins + 1
            """,
            (member.guild.id, day)
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        await self.bot.database.execute(
            """
            INSERT INTO engagement_daily (guild_id, channel_id, user_id, day, messages, reactions)
            VALUES (?, ?, ?, ?, 1, 0)
            ON CONFLICT(guild_id, channel_id, user_id, day)
            DO UPDATE SET messages = messages + 1
            """,
            (message.guild.id, message.channel.id, message.author.id, day)
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or (payload.member and payload.member.bot):
            return
        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        await self.bot.database.execute(
            """
            INSERT INTO engagement_daily (guild_id, channel_id, user_id, day, messages, reactions)
            VALUES (?, ?, ?, ?, 0, 1)
            ON CONFLICT(guild_id, channel_id, user_id, day)
            DO UPDATE SET reactions = reactions + 1
            """,
            (payload.guild_id, payload.channel_id, payload.user_id, day)
        )

    @tasks.loop(hours=3)
    async def auto_refresh_loop(self):
        print("[Member Report] Running background auto-refresh & daily snapshot task...")
        for guild in self.bot.guilds:
            await record_snapshot(self.bot, guild)
            await reconcile_joins_from_members(self.bot, guild)
        await refresh_all_deployed_reports(self.bot)

    @auto_refresh_loop.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(MemberReportCog(bot))
