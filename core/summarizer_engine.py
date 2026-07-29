"""
True Classic Bot - Inner Group Summarizer Engine
Author: Aljay Leodones
Organization: True Classic

Scans Inner Circle / Academy DM channels and produces a mod-ready triage report.

Everything here is deterministic (no external AI service): topics are detected with a
curated keyword taxonomy tuned to the True Classic creator program, and reply state is
derived from who actually spoke last in the channel. That means the same window always
produces the same report, and mods can trust the numbers.
"""

import asyncio
import datetime
import re
from typing import Dict, List, Optional

import discord

import config

# ---------------------------------------------------------------------------
# Timeframe windows
# ---------------------------------------------------------------------------

TIMEFRAMES = {
    "today": {
        "key":       "today",
        "label":     "Today",
        "long":      "Today (since 00:00 UTC)",
        "emoji":     "🕐",
        "fetch_cap": 300,
    },
    "7d": {
        "key":       "7d",
        "label":     "7 Days",
        "long":      "Last 7 Days",
        "emoji":     "📆",
        "fetch_cap": 600,
    },
    "30d": {
        "key":       "30d",
        "label":     "1 Month",
        "long":      "Last 30 Days",
        "emoji":     "🗓️",
        "fetch_cap": 1200,
    },
}


def window_start(timeframe: str, now: datetime.datetime) -> datetime.datetime:
    """Return the UTC cutoff for a timeframe key."""
    if timeframe == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if timeframe == "7d":
        return now - datetime.timedelta(days=7)
    return now - datetime.timedelta(days=30)


# ---------------------------------------------------------------------------
# Topic taxonomy - tuned to the creator / affiliate program workflow
# ---------------------------------------------------------------------------

TOPIC_TAXONOMY = [
    ("Contract & Agreement", "📄", [
        r"\bcontract(s|ual)?\b", r"\bagreement(s)?\b", r"\bsign(ed|ing)?\b", r"\bdocusign\b",
        r"\bpaperwork\b", r"\bterms\b", r"\bnda\b", r"\bw-?9\b", r"\bclause\b", r"\bcountersign",
    ]),
    ("Sizing & Fit", "📐", [
        r"\bsize(s|d|ing)?\b", r"\bfit(s|ted|ting)?\b", r"\bmeasurement(s)?\b", r"\bwaist\b",
        r"\binseam\b", r"\bchest\b", r"\bxs\b", r"\bxl\b", r"\bxxl\b", r"\b[23]xl\b",
        r"\bsmall\b", r"\bmedium\b", r"\blarge\b", r"\btrue to size\b",
    ]),
    ("Sampling & Product", "📦", [
        r"\bsample(s|d|ing)?\b", r"\bproduct(s)?\b", r"\bpima\b", r"\btee(s)?\b", r"\bt-?shirt(s)?\b",
        r"\bshirt(s)?\b", r"\bhoodie(s)?\b", r"\bpolo(s)?\b", r"\bjean(s)?\b", r"\bshort(s)?\b",
        r"\bunderwear\b", r"\bsock(s)?\b", r"\bfabric\b", r"\bcolorway(s)?\b", r"\bpack(age)?\b",
        r"\bbox\b", r"\bdrop\b", r"\bcollection\b", r"\bseed(ing|ed)?\b",
    ]),
    ("Shipping & Tracking", "🚚", [
        r"\bship(s|ped|ping|ment)?\b", r"\btrack(ing)?\b", r"\bdeliver(y|ed|ies)?\b", r"\barriv(e|ed|al)\b",
        r"\baddress\b", r"\bzip ?code\b", r"\busps\b", r"\bfedex\b", r"\bups\b", r"\bdhl\b",
        r"\border(s|ed)?\b", r"\bin transit\b", r"\bcustoms\b", r"\breturn label\b",
    ]),
    ("Content & Posting", "🎬", [
        r"\bvideo(s)?\b", r"\bpost(s|ed|ing)?\b", r"\breel(s)?\b", r"\btiktok\b", r"\binstagram\b",
        r"\big\b", r"\byoutube\b", r"\bshorts?\b", r"\bcontent\b", r"\bfilm(ed|ing)?\b",
        r"\bedit(s|ed|ing)?\b", r"\bupload(s|ed|ing)?\b", r"\bdraft(s)?\b", r"\bscript(s)?\b",
        r"\bhook(s)?\b", r"\bcaption(s)?\b", r"\bugc\b", r"\bbrief(s)?\b", r"\bwhitelist(ing)?\b",
        r"\bspark ?code(s)?\b", r"\bgo ?live\b",
    ]),
    ("Links & Affiliate", "🔗", [
        r"\baffiliate\b", r"\blink(s)?\b", r"\bdiscount code\b", r"\bpromo ?code(s)?\b", r"\bcoupon\b",
        r"\butm\b", r"\blanding page\b", r"\bstorefront\b", r"\bref(erral)? ?link\b", r"\bltk\b",
    ]),
    ("Payments & Commission", "💰", [
        r"\bpay(ment|ments|out|outs|ing)?\b", r"\bpaid\b", r"\binvoice(s|d)?\b", r"\bcommission(s)?\b",
        r"\brate(s)?\b", r"\bbonus(es)?\b", r"\bflat fee\b", r"\bvenmo\b", r"\bpaypal\b", r"\bzelle\b",
        r"\bdirect deposit\b", r"\bcpm\b", r"\bnet ?\d+\b", r"\bcompensation\b",
    ]),
    ("Performance & Metrics", "📈", [
        r"\bview(s)?\b", r"\bconversion(s)?\b", r"\bclick(s)?\b", r"\bsale(s)?\b", r"\brevenue\b",
        r"\bctr\b", r"\broas\b", r"\bgmv\b", r"\banalytics\b", r"\bengagement\b", r"\bimpression(s)?\b",
        r"\bwent viral\b", r"\bperform(ance|ed|ing)?\b",
    ]),
    ("Scheduling & Calls", "📅", [
        r"\bcall(s)?\b", r"\bzoom\b", r"\bmeet(ing|ings)?\b", r"\bschedul(e|ed|ing)\b", r"\bcalendar\b",
        r"\bavailab(le|ility)\b", r"\breschedul(e|ed|ing)\b", r"\bcalendly\b", r"\btime slot\b",
        r"\bdeadline(s)?\b", r"\bdue date\b",
    ]),
    ("Onboarding & Access", "🚪", [
        r"\bonboard(ing|ed)?\b", r"\bwelcome\b", r"\bget started\b", r"\baccess\b", r"\binvite(d|s)?\b",
        r"\bsign ?up\b", r"\bportal\b", r"\bdashboard\b", r"\blogin\b", r"\bcredential(s)?\b",
        r"\binner circle\b", r"\bacademy\b", r"\bprogram\b",
    ]),
    ("Issues & Blockers", "⚠️", [
        r"\bissue(s)?\b", r"\bproblem(s)?\b", r"\bbroken\b", r"\bnot working\b", r"\berror(s)?\b",
        r"\bwrong\b", r"\bmissing\b", r"\bdamaged\b", r"\bdefect(ive)?\b", r"\bdelay(s|ed)?\b",
        r"\brefund\b", r"\bcancel(led|ling)?\b", r"\bconfus(ed|ing)\b", r"\bstuck\b", r"\bcomplaint\b",
        r"\bnever (got|received)\b", r"\bstill (waiting|haven'?t)\b",
    ]),
    ("Personal & Availability", "🧍", [
        r"\bvacation\b", r"\btravel(l)?(ing)?\b", r"\bsick\b", r"\binjur(y|ed|ies)\b", r"\baccident\b",
        r"\brecover(y|ing)\b", r"\bhospital\b", r"\bsurgery\b", r"\bfamily\b", r"\bmoving\b",
        r"\bemergency\b", r"\bbusy\b", r"\bout of town\b", r"\bpersonal\b", r"\bfuneral\b",
    ]),
]

# Phrases that mean "this cannot wait"
URGENCY_PATTERNS = [
    r"\basap\b", r"\burgent(ly)?\b", r"\bright away\b", r"\bimmediately\b", r"\bstill waiting\b",
    r"\bany update(s)?\b", r"\bfollow(ing)? up\b", r"\bbump(ing)?\b", r"\bplease (help|advise)\b",
    r"\bhaven'?t heard\b", r"\bsecond time\b", r"\bby (eod|tomorrow)\b",
]

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

_COMPILED_TOPICS = [
    (name, emoji, [re.compile(p, re.IGNORECASE) for p in pats])
    for name, emoji, pats in TOPIC_TAXONOMY
]
_COMPILED_URGENCY = [re.compile(p, re.IGNORECASE) for p in URGENCY_PATTERNS]


# ---------------------------------------------------------------------------
# Triage buckets
# ---------------------------------------------------------------------------

BUCKETS = {
    "P1": {"order": 1, "emoji": "🔴", "label": "NEEDS REPLY NOW",   "blurb": "A creator is waiting on us. Clear these first."},
    "P2": {"order": 2, "emoji": "🟠", "label": "FOLLOW-UP",         "blurb": "We spoke last but the thread has gone quiet. Nudge them."},
    "P3": {"order": 3, "emoji": "🟡", "label": "MONITOR",           "blurb": "Active and healthy, but there are loose ends to watch."},
    "P4": {"order": 4, "emoji": "🟢", "label": "NO ACTION NEEDED",  "blurb": "Conversation is current and closed out."},
    "P5": {"order": 5, "emoji": "⚪", "label": "NO ACTIVITY",       "blurb": "Nothing in this window. Check if the creator has gone cold."},
    "XX": {"order": 6, "emoji": "🚫", "label": "CHANNEL UNREADABLE", "blurb": "Bot cannot see this channel -- fix permissions or update the roster."},
}

BUCKET_ORDER = ["P1", "P2", "P3", "P4", "P5", "XX"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_author(author, guild: Optional[discord.Guild]) -> str:
    """Return 'bot', 'staff' or 'creator' for a message author."""
    if getattr(author, "bot", False):
        return "bot"

    member = None
    if isinstance(author, discord.Member):
        member = author
    elif guild:
        member = guild.get_member(author.id)

    if member:
        role_ids = {r.id for r in member.roles}
        if config.AUTHORIZED_ROLES and role_ids & set(config.AUTHORIZED_ROLES):
            return "staff"
        perms = member.guild_permissions
        if perms.administrator or perms.manage_guild or perms.manage_messages:
            return "staff"
    return "creator"


def _humanize_delta(delta: datetime.timedelta) -> str:
    total = int(delta.total_seconds())
    if total < 0:
        total = 0
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _one_line(text: str, limit: int = 160) -> str:
    """Flatten a message body to a single trimmed line for the report."""
    cleaned = re.sub(r"\s+", " ", (text or "").replace("\n", " ⏎ ")).strip()
    if not cleaned:
        return "(no text -- attachment / embed only)"
    if len(cleaned) > limit:
        return cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def _detect_topics(blobs: List[str]) -> List[tuple]:
    """Count topic hits across a list of message bodies. Returns [(name, emoji, hits)]."""
    results = []
    for name, emoji, patterns in _COMPILED_TOPICS:
        hits = 0
        for blob in blobs:
            for pat in patterns:
                if pat.search(blob):
                    hits += 1
                    break  # one hit per message per topic
        if hits:
            results.append((name, emoji, hits))
    results.sort(key=lambda r: r[2], reverse=True)
    return results


def _detect_urgency(blobs: List[str]) -> List[str]:
    found = []
    for blob in blobs:
        for pat in _COMPILED_URGENCY:
            m = pat.search(blob)
            if m and m.group(0).lower() not in found:
                found.append(m.group(0).lower())
    return found[:5]


# ---------------------------------------------------------------------------
# Per-channel analysis
# ---------------------------------------------------------------------------

async def analyze_channel(
    bot,
    guild: discord.Guild,
    creator_name: str,
    channel_id: int,
    timeframe: str,
    now: datetime.datetime,
    prev_state: Optional[dict] = None,
) -> dict:
    """Scan one channel and return a structured analysis dict."""
    tf = TIMEFRAMES[timeframe]
    since = window_start(timeframe, now)

    result = {
        "creator":        creator_name,
        "channel_id":     channel_id,
        "channel_name":   f"channel-{channel_id}",
        "bucket":         "P4",
        "reasons":        [],
        "next_steps":     [],
        "signals":        [],
        "topics":         [],
        "open_questions": [],
        "trail":          [],
        "counts":         {"total": 0, "creator": 0, "staff": 0, "bot": 0},
        "new_since_last": 0,
        "attachments":    0,
        "links":          0,
        "last_msg":       None,   # (iso, class, author, preview)
        "last_staff":     None,
        "last_creator":   None,
        "unreplied":      0,
        "reaction_ack":   False,
        "waiting_hours":  None,
        "error":          None,
        "last_message_id": prev_state.get("last_message_id") if prev_state else None,
        "last_message_at": prev_state.get("last_message_at") if prev_state else None,
    }

    # --- resolve channel -----------------------------------------------------
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except Exception as exc:
            result["bucket"] = "XX"
            result["error"] = f"cannot resolve channel ({type(exc).__name__})"
            result["reasons"].append(result["error"])
            result["next_steps"].append(
                "Verify the channel still exists and the bot has View Channel + Read Message History, "
                "then update core/inner_groups.py if the ID changed."
            )
            return result

    result["channel_name"] = getattr(channel, "name", result["channel_name"])

    # --- fetch history -------------------------------------------------------
    messages: List[discord.Message] = []
    try:
        async for msg in channel.history(limit=tf["fetch_cap"], after=since, oldest_first=True):
            messages.append(msg)
    except discord.Forbidden:
        result["bucket"] = "XX"
        result["error"] = "missing Read Message History permission"
        result["reasons"].append(result["error"])
        result["next_steps"].append(
            f"Grant the bot **View Channel** and **Read Message History** in #{result['channel_name']}."
        )
        return result
    except Exception as exc:
        result["bucket"] = "XX"
        result["error"] = f"history fetch failed ({type(exc).__name__}: {exc})"
        result["reasons"].append(result["error"])
        result["next_steps"].append("Re-run the Summarizer for this group; if it repeats, check bot permissions.")
        return result

    # Latest message overall - used when the window itself is empty so the mod
    # still learns when this creator was last heard from.
    latest_overall = messages[-1] if messages else None
    if latest_overall is None:
        try:
            async for msg in channel.history(limit=1):
                latest_overall = msg
        except Exception:
            latest_overall = None

    if latest_overall is not None:
        result["last_message_id"] = latest_overall.id
        result["last_message_at"] = latest_overall.created_at.astimezone(datetime.timezone.utc).isoformat()

    # --- empty window --------------------------------------------------------
    if not messages:
        result["bucket"] = "P5"
        if latest_overall is None:
            result["reasons"].append("no messages found in this channel at all")
            result["next_steps"].append(
                "Channel has never been used -- confirm the creator was actually onboarded into this group."
            )
        else:
            last_dt = latest_overall.created_at.astimezone(datetime.timezone.utc)
            gap = _humanize_delta(now - last_dt)
            cls = _classify_author(latest_overall.author, guild)
            result["last_msg"] = (
                last_dt.strftime("%Y-%m-%d %H:%M UTC"), cls,
                latest_overall.author.display_name, _one_line(latest_overall.clean_content),
            )
            result["reasons"].append(f"silent for the whole window (last message {gap} ago)")
            if cls == "creator":
                result["bucket"] = "P1"
                result["reasons"].append("and the last word was the creator's -- never answered")
                result["next_steps"].append(
                    f"Read back the creator's last message from {gap} ago and reply -- it was never answered."
                )
            else:
                result["next_steps"].append(
                    f"No reply from the creator in {gap}. Send a check-in; if there is still nothing, "
                    "flag them for a re-engagement or offboarding decision."
                )
        return result

    # --- tally ---------------------------------------------------------------
    classes = [_classify_author(m.author, guild) for m in messages]
    for cls in classes:
        result["counts"][cls] += 1
    result["counts"]["total"] = len(messages)

    prev_at = None
    if prev_state and prev_state.get("last_message_at"):
        try:
            prev_at = datetime.datetime.fromisoformat(prev_state["last_message_at"])
        except Exception:
            prev_at = None
    if prev_at:
        result["new_since_last"] = sum(
            1 for m in messages if m.created_at.astimezone(datetime.timezone.utc) > prev_at
        )

    creator_blobs, human_blobs = [], []
    for msg, cls in zip(messages, classes):
        body = msg.clean_content or ""
        if cls != "bot":
            # Bot posts are templated, so they would skew topic detection.
            human_blobs.append(body)
        if cls == "creator":
            creator_blobs.append(body)
            result["attachments"] += len(msg.attachments)
            result["links"] += len(URL_PATTERN.findall(body))

    result["topics"] = _detect_topics(human_blobs)

    urgency = _detect_urgency(creator_blobs)
    if urgency:
        result["signals"].append("Urgency language from creator: " + ", ".join(f'"{u}"' for u in urgency))
    if result["attachments"] or result["links"]:
        result["signals"].append(
            f"Creator shared {result['attachments']} attachment(s) and {result['links']} link(s) "
            "-- likely content to review or approve."
        )
    if result["counts"]["creator"] == 0:
        result["signals"].append("One-way window: only staff/bot posted, the creator said nothing.")
    if result["counts"]["staff"] == 0 and result["counts"]["creator"] > 0:
        result["signals"].append("One-way window: creator posted but no staff member replied at all.")

    # --- conversation trail --------------------------------------------------
    trail_slice = messages[-14:]
    if len(messages) > len(trail_slice):
        result["trail"].append(f"... {len(messages) - len(trail_slice)} earlier message(s) omitted ...")
    for msg, cls in zip(trail_slice, classes[-len(trail_slice):]):
        stamp = msg.created_at.astimezone(datetime.timezone.utc).strftime("%m-%d %H:%M")
        tag = {"staff": "STAFF  ", "creator": "CREATOR", "bot": "BOT    "}[cls]
        extra = ""
        if msg.attachments:
            extra += f" [+{len(msg.attachments)} file]"
        if msg.reactions:
            extra += f" [{sum(r.count for r in msg.reactions)} reaction]"
        result["trail"].append(f"[{stamp}] {tag} {msg.author.display_name}: {_one_line(msg.clean_content, 150)}{extra}")

    # --- reply state ---------------------------------------------------------
    last_staff_idx = max((i for i, c in enumerate(classes) if c == "staff"), default=-1)
    last_creator_idx = max((i for i, c in enumerate(classes) if c == "creator"), default=-1)

    def _stamp(idx):
        m = messages[idx]
        dt = m.created_at.astimezone(datetime.timezone.utc)
        return (dt.strftime("%Y-%m-%d %H:%M UTC"), _humanize_delta(now - dt),
                m.author.display_name, _one_line(m.clean_content))

    last_msg = messages[-1]
    last_dt = last_msg.created_at.astimezone(datetime.timezone.utc)
    result["last_msg"] = (
        last_dt.strftime("%Y-%m-%d %H:%M UTC"), classes[-1],
        last_msg.author.display_name, _one_line(last_msg.clean_content),
    )
    if last_staff_idx >= 0:
        result["last_staff"] = _stamp(last_staff_idx)
    if last_creator_idx >= 0:
        result["last_creator"] = _stamp(last_creator_idx)

    # Creator messages sitting after our last reply = the "missed" block.
    unreplied_idx = [i for i, c in enumerate(classes) if c == "creator" and i > last_staff_idx]
    result["unreplied"] = len(unreplied_idx)

    for i in unreplied_idx:
        body = messages[i].clean_content or ""
        if "?" in body:
            dt = messages[i].created_at.astimezone(datetime.timezone.utc)
            result["open_questions"].append((dt.strftime("%Y-%m-%d %H:%M"), _one_line(body, 220)))
    result["open_questions"] = result["open_questions"][:6]

    creator_waiting = result["unreplied"] > 0
    if creator_waiting:
        oldest_wait_dt = messages[unreplied_idx[0]].created_at.astimezone(datetime.timezone.utc)
        waiting = now - oldest_wait_dt
        result["waiting_hours"] = waiting.total_seconds() / 3600.0
        result["waiting_human"] = _humanize_delta(waiting)

        # Reaction-only acknowledgement: we hearted it but never wrote back.
        if any(messages[i].reactions for i in unreplied_idx):
            result["reaction_ack"] = True
            result["signals"].append(
                "We reacted to the creator's message but never sent a written reply."
            )

    has_blockers = any(name == "Issues & Blockers" for name, _, _ in result["topics"])
    has_personal = any(name == "Personal & Availability" for name, _, _ in result["topics"])

    # --- bucket + reasons ----------------------------------------------------
    if creator_waiting:
        wh = result["waiting_hours"]
        if wh >= 48 or has_blockers or urgency:
            result["bucket"] = "P1"
        elif wh >= 12:
            result["bucket"] = "P1"
        else:
            result["bucket"] = "P2"
        result["reasons"].append(
            f"{result['unreplied']} unanswered creator message(s), oldest waiting {result['waiting_human']}"
        )
        if result["open_questions"]:
            result["reasons"].append(f"{len(result['open_questions'])} open question(s)")
    elif last_staff_idx >= 0 and last_staff_idx == len(messages) - 1:
        staff_dt = messages[last_staff_idx].created_at.astimezone(datetime.timezone.utc)
        quiet = now - staff_dt
        quiet_h = quiet.total_seconds() / 3600.0
        if quiet_h >= 72:
            result["bucket"] = "P2"
            result["reasons"].append(f"we spoke last and the creator has been quiet {_humanize_delta(quiet)}")
        else:
            result["bucket"] = "P3"
            result["reasons"].append(f"ball is in the creator's court ({_humanize_delta(quiet)} since our message)")
    elif classes[-1] == "bot":
        result["bucket"] = "P3"
        result["reasons"].append("last activity was an automated/bot post")
    else:
        result["bucket"] = "P4"
        result["reasons"].append("conversation is current with no outstanding creator message")

    if has_blockers and result["bucket"] in ("P3", "P4"):
        result["bucket"] = "P2"
        result["reasons"].append("issue/blocker keywords present")

    # --- next steps ----------------------------------------------------------
    steps = result["next_steps"]

    if creator_waiting:
        if result["open_questions"]:
            steps.append(
                f"Answer the {len(result['open_questions'])} open question(s) listed above "
                f"-- the oldest has been waiting {result['waiting_human']}."
            )
        else:
            steps.append(
                f"Acknowledge the creator's last {result['unreplied']} message(s) "
                f"(waiting {result['waiting_human']}), even if the answer is 'checking on it'."
            )
        if result["reaction_ack"]:
            steps.append("A reaction is not a reply -- send an actual written response so the thread is unblocked.")

    # Topic-driven suggestions are only useful where a mod actually owes something, or
    # where the topic came up repeatedly. Otherwise they turn into filler.
    topic_steps_allowed = result["bucket"] in ("P1", "P2")
    for name, _emoji, hits in result["topics"][:4]:
        if not topic_steps_allowed and hits < 2:
            continue
        if name == "Contract & Agreement":
            steps.append("Confirm the contract status in writing (sent / signed / countersigned) so it is on record.")
        elif name == "Sizing & Fit":
            steps.append("Record the creator's confirmed size in your roster before the next sample goes out.")
        elif name == "Shipping & Tracking":
            steps.append("Pull the tracking number and post it in-channel so the creator stops asking.")
        elif name == "Sampling & Product":
            steps.append("Confirm which products are going out next and whether the creator agreed to them.")
        elif name == "Content & Posting":
            steps.append("Check whether promised content actually went live; if yes, review and give feedback.")
        elif name == "Links & Affiliate":
            steps.append("Verify the creator's affiliate link / code is live and pointing to the right place.")
        elif name == "Payments & Commission":
            steps.append("Escalate the payment question to whoever owns payouts and give the creator a date.")
        elif name == "Scheduling & Calls":
            steps.append("Lock the call time in the calendar and confirm it back in-channel.")
        elif name == "Issues & Blockers":
            steps.append("Treat this as a complaint: name the problem, state the fix, give a timeline.")
        elif name == "Personal & Availability":
            steps.append("Note the creator's stated availability and push deadlines out instead of chasing them.")
        elif name == "Onboarding & Access":
            steps.append("Verify the creator has access to every channel and resource the program promises.")
        elif name == "Performance & Metrics":
            steps.append("Share the numbers they asked about, or say when you can.")

    if has_personal:
        steps.append("Lead the reply with a human check-in before any business ask.")

    if not creator_waiting and result["bucket"] == "P2":
        steps.append("Send a short nudge referencing your last message so the thread restarts.")

    if result["bucket"] in ("P3", "P4") and not steps:
        steps.append("Nothing owed right now. Skim the trail so you have context if they message you today.")

    # De-duplicate while keeping order, cap the list so it stays actionable.
    seen, deduped = set(), []
    for s in steps:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    result["next_steps"] = deduped[:6]

    return result


# ---------------------------------------------------------------------------
# Group scan
# ---------------------------------------------------------------------------

async def scan_group(
    bot,
    guild: discord.Guild,
    group: dict,
    timeframe: str,
    progress_cb=None,
) -> dict:
    """Scan every channel in a group. Returns a full scan payload."""
    now = datetime.datetime.now(datetime.timezone.utc)
    since = window_start(timeframe, now)
    channels = group["channels"]

    prev_rows = await bot.database.fetchall(
        "SELECT * FROM summarizer_channel_state WHERE guild_id = ? AND group_key = ?",
        (guild.id, group["key"]),
    )
    prev_state = {row["channel_id"]: dict(row) for row in prev_rows}

    prev_run = await bot.database.fetchone(
        """
        SELECT * FROM summarizer_runs
        WHERE guild_id = ? AND group_key = ?
        ORDER BY id DESC LIMIT 1
        """,
        (guild.id, group["key"]),
    )

    results = []
    total = len(channels)
    for idx, (creator_name, channel_id) in enumerate(channels.items(), start=1):
        analysis = await analyze_channel(
            bot, guild, creator_name, channel_id, timeframe, now,
            prev_state.get(channel_id),
        )
        results.append(analysis)

        if progress_cb and (idx % 5 == 0 or idx == total):
            try:
                await progress_cb(idx, total, creator_name)
            except Exception:
                pass

        await asyncio.sleep(0.35)  # stay friendly with the REST rate limiter

    # Persist per-channel state so the next report can flag what is new.
    for r in results:
        await bot.database.execute(
            """
            INSERT INTO summarizer_channel_state
                (guild_id, channel_id, group_key, last_message_id, last_message_at, last_status, last_reported_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                group_key        = excluded.group_key,
                last_message_id  = COALESCE(excluded.last_message_id, summarizer_channel_state.last_message_id),
                last_message_at  = COALESCE(excluded.last_message_at, summarizer_channel_state.last_message_at),
                last_status      = excluded.last_status,
                last_reported_at = datetime('now')
            """,
            (guild.id, r["channel_id"], group["key"], r["last_message_id"], r["last_message_at"], r["bucket"]),
        )

    return {
        "group":      group,
        "timeframe":  timeframe,
        "now":        now,
        "since":      since,
        "results":    results,
        "prev_run":   dict(prev_run) if prev_run else None,
        "totals":     _totals(results),
    }


def _totals(results: List[dict]) -> dict:
    buckets = {k: 0 for k in BUCKET_ORDER}
    for r in results:
        buckets[r["bucket"]] += 1
    return {
        "channels":       len(results),
        "messages":       sum(r["counts"]["total"] for r in results),
        "creator_msgs":   sum(r["counts"]["creator"] for r in results),
        "staff_msgs":     sum(r["counts"]["staff"] for r in results),
        "bot_msgs":       sum(r["counts"]["bot"] for r in results),
        "active":         sum(1 for r in results if r["counts"]["total"] > 0),
        "new_messages":   sum(r["new_since_last"] for r in results),
        "unreplied":      sum(r["unreplied"] for r in results),
        "open_questions": sum(len(r["open_questions"]) for r in results),
        "buckets":        buckets,
    }


def sorted_results(results: List[dict]) -> List[dict]:
    """Most urgent first; inside a bucket, longest wait first."""
    def key(r):
        return (
            BUCKETS[r["bucket"]]["order"],
            -(r["waiting_hours"] or 0),
            -len(r["open_questions"]),
            r["creator"].lower(),
        )
    return sorted(results, key=key)


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------

WIDE = "=" * 94
THIN = "-" * 94
HASH = "#" * 94


def build_report_text(scan: dict, requester: str) -> str:
    group = scan["group"]
    tf = TIMEFRAMES[scan["timeframe"]]
    now = scan["now"]
    since = scan["since"]
    t = scan["totals"]
    ordered = sorted_results(scan["results"])

    L: List[str] = []
    add = L.append

    # ---- header ----
    add(WIDE)
    add(f"  TRUE CLASSIC  -  {group['label'].upper()}  -  MOD SUMMARY REPORT")
    add(WIDE)
    add(f"  Group ............. {group['label']}  ({t['channels']} channels)")
    add(f"  Window ............ {tf['long']}   [{since.strftime('%Y-%m-%d %H:%M')} -> {now.strftime('%Y-%m-%d %H:%M')} UTC]")
    add(f"  Generated ......... {now.strftime('%Y-%m-%d %H:%M UTC')}   by {requester}")
    if scan["prev_run"]:
        pr = scan["prev_run"]
        add(f"  Previous report ... {pr['created_at']} UTC  ({pr['timeframe']} window)")
        add(f"  New messages ...... {t['new_messages']} since that report")
    else:
        add("  Previous report ... none on record -- this is the first run for this group")
    add(THIN)
    add("  AT A GLANCE")
    add(f"    Messages in window ......... {t['messages']}  (creators {t['creator_msgs']} | staff {t['staff_msgs']} | bot {t['bot_msgs']})")
    add(f"    Channels with activity ..... {t['active']} / {t['channels']}")
    add(f"    Unanswered creator msgs .... {t['unreplied']}")
    add(f"    Open questions ............. {t['open_questions']}")
    for bk in BUCKET_ORDER:
        cnt = t["buckets"][bk]
        if cnt:
            b = BUCKETS[bk]
            add(f"    {b['emoji']} {b['label']:<20} {cnt}")
    add(WIDE)
    add("")

    # ---- triage board ----
    add("  TRIAGE BOARD  -  work this list from the top down")
    add(THIN)
    for bk in BUCKET_ORDER:
        group_items = [r for r in ordered if r["bucket"] == bk]
        if not group_items:
            continue
        b = BUCKETS[bk]
        add(f"  {b['emoji']} {b['label']} ({len(group_items)})  -- {b['blurb']}")
        for i, r in enumerate(group_items, start=1):
            wait = f"oldest {r['waiting_human']}" if r.get("waiting_human") else "-"
            add(f"     {i:>2}. #{r['channel_name']:<26} {wait:<17} {r['reasons'][0] if r['reasons'] else ''}")
        add("")
    add(WIDE)
    add("")

    # ---- worksheet ----
    add("  MOD WORKSHEET  -  copy this block into your notes and tick items off")
    add("  (only channels that owe someone something -- 🟡 monitor and 🟢 closed are left out)")
    add(THIN)
    worksheet_rows = 0
    for r in ordered:
        if r["bucket"] in ("P3", "P4"):
            continue
        for step in r["next_steps"][:3]:
            add(f"  [ ] #{r['channel_name']:<26} {BUCKETS[r['bucket']]['emoji']}  {step}")
            worksheet_rows += 1
        if r["next_steps"]:
            add("")
    if worksheet_rows == 0:
        add("  Nothing outstanding across this group for the selected window. Nice.")
    add(WIDE)
    add("")

    # ---- how to read ----
    add("  HOW TO USE THIS REPORT")
    add(THIN)
    add("  1. Clear every 🔴 channel first -- a creator is actively waiting in each one.")
    add("  2. Then work 🟠: we spoke last and the thread stalled. A one-line nudge is usually enough.")
    add("  3. 🟡 needs a skim only. 🟢 is closed out -- skip it.")
    add("  4. ⚪ means no activity in the window. Two ⚪ reports in a row = decide re-engage or offboard.")
    add("  5. After you reply, post the outcome in-channel so the next mod inherits the context.")
    add("  6. Re-run the Summarizer at the end of your shift -- 'New messages since that report'")
    add("     tells you exactly what moved while you were working.")
    add("")
    add("  Topics and reply state are detected from message text and message order -- treat them as")
    add("  a triage aid, and always read the conversation trail before replying to a creator.")
    add(WIDE)
    add("")
    add("")

    # ---- per channel ----
    add("  PER-CHANNEL DETAIL")
    add("")
    for r in ordered:
        b = BUCKETS[r["bucket"]]
        add(HASH)
        add(f"  #{r['channel_name']}   -   creator: {r['creator']}   -   {b['emoji']} {b['label']}")
        add(HASH)
        add(f"  Channel ID ........ {r['channel_id']}")

        if r["error"]:
            add(f"  STATUS ............ UNREADABLE -- {r['error']}")
            for i, step in enumerate(r["next_steps"], start=1):
                add(f"  FIX {i} ............. {step}")
            add("")
            continue

        c = r["counts"]
        new_txt = f"   • {r['new_since_last']} new since last report" if r["new_since_last"] else ""
        add(f"  Activity .......... {c['total']} message(s) (creator {c['creator']} | staff {c['staff']} | bot {c['bot']}){new_txt}")

        if r["last_msg"]:
            stamp, cls, author, preview = r["last_msg"]
            add(f"  Last message ...... {stamp}  by {author} ({cls.upper()})")
            add(f"                      \"{preview}\"")
        if r["last_staff"]:
            stamp, ago, author, _p = r["last_staff"]
            add(f"  Last staff reply .. {stamp}  ({ago} ago, {author})")
        else:
            add("  Last staff reply .. none in this window")
        if r["last_creator"]:
            stamp, ago, author, _p = r["last_creator"]
            add(f"  Last creator msg .. {stamp}  ({ago} ago, {author})")

        add(f"  Reply state ....... {'; '.join(r['reasons']) if r['reasons'] else 'n/a'}")

        if r["topics"]:
            add("")
            add("  TOPICS DISCUSSED (messages mentioning each)")
            for name, emoji, hits in r["topics"][:8]:
                bar = "#" * min(hits, 20)
                add(f"    {emoji} {name:<26} {hits:>3}  {bar}")

        if r["open_questions"]:
            add("")
            add("  OPEN QUESTIONS FROM CREATOR (no staff reply after these)")
            for i, (stamp, text) in enumerate(r["open_questions"], start=1):
                add(f"    {i}. [{stamp}] \"{text}\"")

        if r["signals"]:
            add("")
            add("  SIGNALS")
            for s in r["signals"]:
                add(f"    ! {s}")

        if r["trail"]:
            add("")
            add("  CONVERSATION TRAIL (oldest first, trimmed)")
            for line in r["trail"]:
                add(f"    {line}")

        if r["next_steps"]:
            add("")
            add("  NEXT STEPS FOR MOD")
            for i, step in enumerate(r["next_steps"], start=1):
                add(f"    {i}. {step}")

        add("")
        add("")

    add(WIDE)
    add(f"  END OF REPORT  -  {group['label']}  -  {tf['long']}  -  generated {now.strftime('%Y-%m-%d %H:%M UTC')}")
    add(f"  True Classic Community Operations Bot  -  requested by {requester}")
    add(WIDE)

    return "\n".join(L)


def report_filename(scan: dict) -> str:
    group = scan["group"]
    stamp = scan["now"].strftime("%Y-%m-%d_%H%M")
    return f"{group['slug']}_summary_{scan['timeframe']}_{stamp}.txt"
