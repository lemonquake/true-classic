"""
True Classic Bot - Creator Care Engine
Author: Aljay Leodones
Organization: True Classic

Turns a Summarizer scan into a **Creator Care Brief** -- a customer-care oriented
text file with one quick-reference card per creator channel.

Where the triage report answers "who is waiting on us", this answers the next
question a mod actually has: "I am about to reply to this person -- what do I need
to know so the reply feels personal instead of copy-pasted?"

Per creator it surfaces: their most common topics, what they keep asking about, the
messages we missed, the issues they raised, the promises we made them, the personal
details they shared, their wins, how fast we normally answer them, when they are
usually online, how they write, and a draft opener with fill-in placeholders.

Everything is derived from the messages in the scanned window -- same as the
triage engine, there is no external AI call and no invented detail. Every quote in
the brief is a real line a real person typed. Anything a mod still has to supply is
left as an explicit {{placeholder}}.
"""

import calendar
import datetime
import re
import textwrap
from typing import Dict, List, Optional, Tuple

from core import summarizer_engine as engine

# Shared formatting helpers -- keep the two reports looking like one product.
one_line = engine._one_line
humanize = engine._humanize_delta

WIDE = "=" * 94
THIN = "-" * 94
HASH = "#" * 94


# ---------------------------------------------------------------------------
# Care lexicons
# ---------------------------------------------------------------------------

POSITIVE_PATTERNS = [
    r"\bthank(s| you)\b", r"\bappreciate\b", r"\bawesome\b", r"\bamazing\b", r"\bexcited\b",
    r"\bstoked\b", r"\bpumped\b", r"\blove (it|this|that|the|these|them)\b", r"\bperfect\b",
    r"\bincredible\b", r"\bkiller\b", r"\bfire\b", r"\blet'?s go\b", r"\bsounds good\b",
    r"\bwill do\b", r"\bno worries\b", r"\bno rush\b", r"\ball good\b", r"\bhappy\b", r"\bglad\b",
    r"\bgrateful\b", r"\bobsessed\b", r"\bcrushed it\b", r"\bgreat\b", r"\bdope\b", r"\bfavorite\b",
    r"\bmy pleasure\b", r"\bbeautiful\b", r"\bquality\b", r"🔥|🙏|❤️|😍|🙌|💪|🤝|🥳",
]

NEGATIVE_PATTERNS = [
    r"\bfrustrat(ed|ing)\b", r"\bannoy(ed|ing)\b", r"\bdisappoint(ed|ing|ment)\b", r"\bupset\b",
    r"\bunhappy\b", r"\bnot happy\b", r"\bridiculous\b", r"\bunacceptable\b", r"\bignor(ed|ing)\b",
    r"\bno response\b", r"\bstill waiting\b", r"\bstill (haven'?t|no|not)\b", r"\bconfus(ed|ing)\b",
    r"\bworried\b", r"\bconcern(ed|s)\b", r"\bsucks\b", r"\bterrible\b", r"\bawful\b", r"\bangry\b",
    r"\bbummed\b", r"\bwtf\b", r"\bnever (got|received|heard)\b", r"\bcancel(l)?(ing|ed)?\b",
    r"\brefund\b", r"\bwaste of\b", r"\bfed up\b", r"\b(second|third|fourth) time\b",
    r"\bgiving up\b", r"\bdone waiting\b", r"\bnot okay\b", r"\bthis is (bad|not)\b",
]

# Any one of these means the relationship needs a human, not a template.
STRONG_NEGATIVE_PATTERNS = [
    r"\bunacceptable\b", r"\bridiculous\b", r"\bfrustrat(ed|ing)\b", r"\bfed up\b",
    r"\bstill waiting\b", r"\bnever (got|received|heard)\b", r"\bcancel(l)?(ing|ed)?\b",
    r"\brefund\b", r"\bignor(ed|ing)\b", r"\bwaste of\b", r"\b(third|fourth) time\b",
    r"\bnot happy\b", r"\bdone waiting\b", r"\bgiving up\b",
]

# Things worth thanking them for out loud.
WIN_PATTERNS = [
    r"\bwent viral\b", r"\bblew up\b", r"\bpopping off\b", r"\bbest (seller|selling)\b",
    r"\bsold out\b", r"\bcrushed it\b", r"\bmy go-?to\b", r"\bfavorite (tee|shirt|fit|piece|brand)\b",
    r"\bobsessed\b", r"\bso many (views|sales|comments|dms|orders)\b", r"\bhighest (views|sales)\b",
    r"\bthank you so much\b", r"\bappreciate you\b", r"\bbiggest (video|post|month)\b",
    r"\bpeople keep asking\b", r"\bbest (fit|tee|shirt|quality)\b", r"\bcan'?t wait\b",
    r"\bposted (it|the|my)\b", r"\bgot great (feedback|response)\b", r"\bdid (really )?well\b",
]

# Staff language that creates an expectation. Detected on staff messages only.
COMMITMENT_PATTERNS = [
    r"\bi'?ll\b", r"\bwe'?ll\b", r"\bi will\b", r"\bwe will\b", r"\bi'?m going to\b",
    r"\blet me (check|confirm|look|find|ask|get|see|dig)\b",
    r"\bwill (send|ship|get|check|update|confirm|follow up|reach out|email|dm|post)\b",
    r"\bgetting (that|this|it|them) (sent|out|over|ready)\b", r"\bon it\b", r"\bcircle back\b",
    r"\bkeep you posted\b", r"\bget back to you\b", r"\bsending (it|that|those|them) (over|out|now|today)\b",
    r"\bby (eod|tomorrow|monday|tuesday|wednesday|thursday|friday|end of (the )?(day|week))\b",
    r"\bshould (be|have|go out|arrive|ship)\b", r"\bworking on (it|that)\b",
]

# Extra personal-life hooks on top of the taxonomy's Personal & Availability bucket.
PERSONAL_EXTRA_PATTERNS = [
    r"\bbirthday\b", r"\bwedding\b", r"\bengaged\b", r"\bbaby\b", r"\bnewborn\b", r"\bkids?\b",
    r"\bdaughter\b", r"\bson\b", r"\bwife\b", r"\bhusband\b", r"\bgirlfriend\b", r"\bboyfriend\b",
    r"\bdog\b", r"\bpuppy\b", r"\bnew job\b", r"\bgraduat(ed|ion)\b", r"\bcompetition\b",
    r"\bmarathon\b", r"\bgym\b", r"\bcut\b", r"\bbulk\b", r"\bnew (place|apartment|house)\b",
    r"\bexams?\b", r"\bschool\b", r"\bholiday(s)?\b", r"\bthanksgiving\b", r"\bchristmas\b",
]

_C_POSITIVE  = [re.compile(p, re.IGNORECASE) for p in POSITIVE_PATTERNS]
_C_NEGATIVE  = [re.compile(p, re.IGNORECASE) for p in NEGATIVE_PATTERNS]
_C_STRONGNEG = [re.compile(p, re.IGNORECASE) for p in STRONG_NEGATIVE_PATTERNS]
_C_WINS      = [re.compile(p, re.IGNORECASE) for p in WIN_PATTERNS]
_C_COMMIT    = [re.compile(p, re.IGNORECASE) for p in COMMITMENT_PATTERNS]
_C_PERSONAL_EXTRA = [re.compile(p, re.IGNORECASE) for p in PERSONAL_EXTRA_PATTERNS]


def _taxonomy_patterns(topic_name: str):
    for name, _emoji, pats in engine._COMPILED_TOPICS:
        if name == topic_name:
            return pats
    return []


_C_ISSUES   = _taxonomy_patterns("Issues & Blockers")
_C_PERSONAL = _taxonomy_patterns("Personal & Availability") + _C_PERSONAL_EXTRA

EMOJI_RE = re.compile(
    r"(?:<a?:\w+:\d+>)|[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿⬀-⯿]"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|\s+•\s+")
_Q_STARTER = re.compile(
    r"^(who|what|when|where|why|how|which|whose|can|could|would|will|should|do|does|did|is|are|was|were|any|got|have|has|may|might|shall)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Mood / tier scales
# ---------------------------------------------------------------------------

MOODS = {
    "frustrated": {"emoji": "😠", "label": "Frustrated", "order": 0,
                   "note": "Handle personally. Own the miss before anything else."},
    "cooling":    {"emoji": "😕", "label": "Cooling",    "order": 1,
                   "note": "Patience is thinning. Be specific and give a date."},
    "neutral":    {"emoji": "😐", "label": "Neutral",    "order": 2,
                   "note": "Transactional so far. A warm touch goes a long way."},
    "warm":       {"emoji": "🙂", "label": "Warm",       "order": 3,
                   "note": "Good rapport. Keep it going, keep it human."},
    "positive":   {"emoji": "😄", "label": "Positive",   "order": 4,
                   "note": "Big fan. Great candidate for asks and upsells."},
    "nosignal":   {"emoji": "🔇", "label": "No Signal",  "order": 5,
                   "note": "They said nothing in this window -- nothing to read into."},
}

TIERS = {
    "top":    {"emoji": "⭐", "label": "Top Voice"},
    "steady": {"emoji": "🔵", "label": "Steady"},
    "light":  {"emoji": "🔹", "label": "Light"},
    "silent": {"emoji": "🔇", "label": "Silent"},
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _is_question(sentence: str) -> bool:
    if len(sentence) < 10:
        return False
    if "?" in sentence:
        return True
    # "How does the link work" with no question mark still counts, but only if the
    # sentence is long enough that it is not something like "Will do".
    return bool(_Q_STARTER.match(sentence)) and len(sentence) >= 22


def _hits(text: str, compiled) -> int:
    return sum(1 for pat in compiled if pat.search(text or ""))


def _matched_tokens(text: str, compiled) -> List[str]:
    out = []
    for pat in compiled:
        m = pat.search(text or "")
        if m:
            tok = re.sub(r"\s+", " ", m.group(0)).strip().lower()
            if tok and tok not in out:
                out.append(tok)
    return out


def _clip(text: str, width: int) -> str:
    """Trim to width on a word boundary so quotes never end mid-word."""
    text = (text or "").strip()
    if len(text) <= width:
        return text
    cut = text[: width - 1]
    if " " in cut[width // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-") + "…"


def _wrap_text(prefix: str, text: str, width: int = 94, hang: Optional[str] = None) -> List[str]:
    """Emit 'PREFIX text', folded at `width` with a hanging indent. Nothing gets cut."""
    hang = hang if hang is not None else " " * len(prefix)
    body = re.sub(r"\s+", " ", (text or "").strip())
    chunks = textwrap.wrap(
        body, width=max(20, width - len(prefix)),
        break_long_words=False, break_on_hyphens=False,
    ) or [""]
    return [prefix + chunks[0]] + [hang + chunk for chunk in chunks[1:]]


def _wrap_parts(prefix: str, parts: List[str], sep: str = "  •  ", width: int = 88) -> List[str]:
    """Render 'PREFIX a • b • c', folding onto indented continuation lines."""
    parts = [p for p in parts if p]
    if not parts:
        return []
    pad = " " * len(prefix)
    lines, cur, cur_len = [], [], len(prefix)
    for part in parts:
        extra = len(part) + (len(sep) if cur else 0)
        if cur and cur_len + extra > width:
            lines.append((prefix if not lines else pad) + sep.join(cur))
            cur, cur_len = [part], len(pad) + len(part)
        else:
            cur.append(part)
            cur_len += extra
    if cur:
        lines.append((prefix if not lines else pad) + sep.join(cur))
    return lines


def _median(values: list):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _quote_hunt(records, compiled, cls: str = "creator", limit: int = 4, min_len: int = 12):
    """Pull real sentences matching a lexicon. Returns [(stamp, sentence)]."""
    out, seen = [], set()
    for rec in records:
        if rec["cls"] != cls:
            continue
        for sentence in _split_sentences(rec["content"]):
            if len(sentence) < min_len:
                continue
            if any(pat.search(sentence) for pat in compiled):
                key = sentence.lower()[:70]
                if key in seen:
                    continue
                seen.add(key)
                out.append((rec["ts"].strftime("%m-%d %H:%M"), one_line(sentence, 200)))
                break
        if len(out) >= limit:
            break
    return out


def _topics_of(text: str) -> List[Tuple[str, str]]:
    found = []
    for name, emoji, pats in engine._COMPILED_TOPICS:
        if any(pat.search(text or "") for pat in pats):
            found.append((name, emoji))
    return found


def _best_window(hours: List[int]) -> Optional[Tuple[int, int, int]]:
    """Densest 3-hour block of creator activity. Returns (start, end, count)."""
    if not hours:
        return None
    counts = [0] * 24
    for h in hours:
        counts[h] += 1
    best_start, best_sum = 0, -1
    for start in range(24):
        total = sum(counts[(start + i) % 24] for i in range(3))
        if total > best_sum:
            best_sum, best_start = total, start
    if best_sum <= 0:
        return None
    return best_start, (best_start + 3) % 24, best_sum


def _reply_deltas(records) -> List[datetime.timedelta]:
    """How long the creator waited each time before a staff member answered."""
    deltas, waiting_since = [], None
    for rec in records:
        if rec["cls"] == "creator":
            if waiting_since is None:
                waiting_since = rec["ts"]
        elif rec["cls"] == "staff" and waiting_since is not None:
            deltas.append(rec["ts"] - waiting_since)
            waiting_since = None
    return deltas


# ---------------------------------------------------------------------------
# Per-creator profile
# ---------------------------------------------------------------------------

def profile_channel(r: dict, now: datetime.datetime) -> dict:
    """Build one care profile from a Summarizer channel analysis."""
    records = r.get("records") or []
    creator_recs = [x for x in records if x["cls"] == "creator"]
    staff_recs = [x for x in records if x["cls"] == "staff"]

    p = {
        "creator":       r["creator"],
        "channel_id":    r["channel_id"],
        "channel_name":  r["channel_name"],
        "bucket":        r["bucket"],
        "error":         r.get("error"),
        "counts":        r["counts"],
        "creator_msgs":  r["counts"]["creator"],
        "topics":        r["topics"],
        "waiting_human": r.get("waiting_human"),
        "waiting_hours": r.get("waiting_hours"),
        "reaction_ack":  r.get("reaction_ack", False),
        "attachments":   r.get("attachments", 0),
        "links":         r.get("links", 0),
        "last_msg":      r.get("last_msg"),
        "last_staff":    r.get("last_staff"),
        "last_creator":  r.get("last_creator"),
        "reasons":       r.get("reasons", []),
        "next_steps":    r.get("next_steps", []),
        # filled below
        "missed":         [],
        "questions":      [],
        "repeat_asks":    [],
        "issues":         [],
        "issue_tokens":   [],
        "commitments":    [],
        "personal":       [],
        "wins":           [],
        "mood":           "nosignal",
        "mood_score":     0.0,
        "style":          [],
        "style_lead":     None,
        "avg_words":      0.0,
        "reply_median":   None,
        "reply_slowest":  None,
        "reply_samples":  0,
        "best_window":    None,
        "best_days":      [],
        "days_silent":    None,
        "tier":           "silent",
        "flags":          [],
        "care_score":     0,
        "headline":       "",
        "handling":       [],
        "avoid":          [],
        "opener":         "",
    }

    # --- how long since we last heard anything at all ------------------------
    if r.get("last_message_at"):
        try:
            last_at = datetime.datetime.fromisoformat(r["last_message_at"])
            p["days_silent"] = max(0.0, (now - last_at).total_seconds() / 86400.0)
        except Exception:
            p["days_silent"] = None

    if r["bucket"] == "XX":
        p["headline"] = f"Channel unreadable -- {r.get('error') or 'unknown reason'}."
        p["flags"].append("🚫 UNREADABLE")
        return p

    # --- missed messages: creator lines after our last reply -----------------
    last_staff_idx = max((i for i, x in enumerate(records) if x["cls"] == "staff"), default=-1)
    for rec in records[last_staff_idx + 1:]:
        if rec["cls"] != "creator":
            continue
        extra = ""
        if rec["attachments"]:
            extra = f" [+{rec['attachments']} file]"
        p["missed"].append((
            rec["ts"].strftime("%m-%d %H:%M"),
            humanize(now - rec["ts"]),
            one_line(rec["content"], 260) + extra,
        ))
    p["missed"] = p["missed"][:8]

    # --- questions + repeat asks --------------------------------------------
    topic_ask_msgs: Dict[str, dict] = {}
    for idx, rec in enumerate(records):
        if rec["cls"] != "creator":
            continue
        # A question is "answered" only if a staff message came after it.
        answered = last_staff_idx > idx
        # A bare "what's the process for a replacement?" carries no keyword of its own,
        # so fall back to the subject of the message it was asked in.
        msg_topics = _topics_of(rec["content"])
        for sentence in _split_sentences(rec["content"]):
            if not _is_question(sentence):
                continue
            topics = _topics_of(sentence) or msg_topics
            p["questions"].append({
                "stamp":    rec["ts"].strftime("%m-%d %H:%M"),
                "text":     one_line(sentence, 220),
                "topics":   topics,
                "answered": answered,
            })
            for name, emoji in topics:
                slot = topic_ask_msgs.setdefault(name, {"emoji": emoji, "msgs": set()})
                slot["msgs"].add(rec["id"])
    p["questions"] = p["questions"][:12]
    # Counted per message, not per sentence -- two questions in one message is one ask.
    p["repeat_asks"] = sorted(
        [(name, v["emoji"], len(v["msgs"])) for name, v in topic_ask_msgs.items() if len(v["msgs"]) >= 2],
        key=lambda x: x[2], reverse=True,
    )[:4]

    # --- issues, commitments, personal notes, wins ---------------------------
    p["issues"] = _quote_hunt(records, _C_ISSUES, "creator", limit=4)
    p["personal"] = _quote_hunt(records, _C_PERSONAL, "creator", limit=3)
    p["wins"] = _quote_hunt(records, _C_WINS, "creator", limit=3)

    tokens = []
    for rec in creator_recs:
        for tok in _matched_tokens(rec["content"], _C_ISSUES):
            if tok not in tokens:
                tokens.append(tok)
    p["issue_tokens"] = tokens[:8]

    # A staff promise counts as "open" when the creator wrote again afterwards
    # (they came back, so from their side it is unresolved) or when it is the last
    # thing we said and they are still waiting.
    creator_ts = [rec["ts"] for rec in creator_recs]
    for rec in staff_recs:
        for sentence in _split_sentences(rec["content"]):
            if len(sentence) < 12 or not any(pat.search(sentence) for pat in _C_COMMIT):
                continue
            followed_up = any(ts > rec["ts"] for ts in creator_ts)
            p["commitments"].append({
                "stamp":       rec["ts"].strftime("%m-%d %H:%M"),
                "age":         humanize(now - rec["ts"]),
                "author":      rec["author"],
                "text":        one_line(sentence, 200),
                "followed_up": followed_up,
            })
            break
    # Newest first, and prefer the ones the creator chased.
    p["commitments"] = sorted(
        p["commitments"], key=lambda c: (not c["followed_up"],)
    )[:4]

    # --- mood ---------------------------------------------------------------
    pos = sum(_hits(rec["content"], _C_POSITIVE) for rec in creator_recs)
    neg = sum(_hits(rec["content"], _C_NEGATIVE) for rec in creator_recs)
    strong = sum(_hits(rec["content"], _C_STRONGNEG) for rec in creator_recs)

    if not creator_recs:
        p["mood"] = "nosignal"
    else:
        score = (pos - neg) / max(1, len(creator_recs))
        p["mood_score"] = round(score, 2)
        if strong >= 2:
            p["mood"] = "frustrated"
        elif score <= -0.30:
            p["mood"] = "frustrated"
        elif strong >= 1 or score <= -0.05:
            p["mood"] = "cooling"
        elif score < 0.20:
            p["mood"] = "neutral"
        elif score < 0.50 or pos < 2:
            # One "thanks" is politeness, not enthusiasm -- do not call it Positive.
            p["mood"] = "warm"
        else:
            p["mood"] = "positive"

    # --- writing style ------------------------------------------------------
    texts = [rec["content"] for rec in creator_recs if (rec["content"] or "").strip()]
    # Three messages is the floor for calling something a habit rather than a coincidence.
    if len(texts) >= 3:
        word_counts = [len(t.split()) for t in texts]
        p["avg_words"] = round(sum(word_counts) / len(word_counts), 1)
        emoji_msgs = sum(1 for t in texts if EMOJI_RE.search(t))
        caps_msgs = sum(
            1 for t in texts
            if len(t) > 14 and sum(c.isupper() for c in t) / max(1, sum(c.isalpha() for c in t)) > 0.7
        )
        if p["avg_words"] <= 12:
            p["style_lead"] = f"writes short ({p['avg_words']} words avg) -- keep replies tight"
        elif p["avg_words"] >= 40:
            p["style_lead"] = f"writes long ({p['avg_words']} words avg) -- answer every point, use bullets"
        else:
            p["style_lead"] = f"average message {p['avg_words']} words"
        p["style"].append(p["style_lead"])
        if emoji_msgs and emoji_msgs / len(texts) >= 0.3:
            p["style"].append("casual / emoji-friendly -- match the energy")
        if caps_msgs:
            p["style"].append(f"{caps_msgs} message(s) in caps -- read as emphasis or heat")
    if p["attachments"]:
        p["style"].append(f"sends media ({p['attachments']} attachment(s) this window)")
    if p["links"]:
        p["style"].append(f"shares links ({p['links']} this window)")

    # --- our responsiveness to THIS creator ---------------------------------
    deltas = _reply_deltas(records)
    if deltas:
        p["reply_samples"] = len(deltas)
        p["reply_median"] = _median(deltas)
        p["reply_slowest"] = max(deltas)

    # --- when they are around ----------------------------------------------
    # Only claim a pattern when there are enough messages to actually be one.
    if len(creator_recs) >= 3:
        p["best_window"] = _best_window([rec["ts"].hour for rec in creator_recs])
    if len(creator_recs) >= 5:
        day_counts: Dict[int, int] = {}
        for rec in creator_recs:
            day_counts[rec["ts"].weekday()] = day_counts.get(rec["ts"].weekday(), 0) + 1
        p["best_days"] = [
            calendar.day_abbr[d]
            for d, _c in sorted(day_counts.items(), key=lambda kv: kv[1], reverse=True)[:2]
        ]

    return p


# ---------------------------------------------------------------------------
# Flags, score, headline, handling guidance
# ---------------------------------------------------------------------------

def _finalize_profile(p: dict, now: datetime.datetime) -> None:
    """Second pass -- needs the profile complete, adds the mod-facing verdict."""
    if p["bucket"] == "XX":
        return

    open_qs = [q for q in p["questions"] if not q["answered"]]
    p["open_questions"] = open_qs
    wh = p["waiting_hours"] or 0
    score = 0

    # --- flags --------------------------------------------------------------
    if p["missed"]:
        p["flags"].append(f"⏳ WAITING {p['waiting_human'] or 'unknown'}")
    if p["mood"] == "frustrated":
        p["flags"].append("😠 UNHAPPY")
    elif p["mood"] == "cooling":
        p["flags"].append("😕 PATIENCE THIN")
    if p["issues"]:
        p["flags"].append(f"⚠️ {len(p['issues'])} ISSUE(S) RAISED")
    if open_qs:
        p["flags"].append(f"❓ {len(open_qs)} OPEN QUESTION(S)")
    if p["repeat_asks"]:
        p["flags"].append("🔁 REPEAT ASK")
    if any(c["followed_up"] for c in p["commitments"]):
        p["flags"].append("🤝 PROMISE OUTSTANDING")
    if p["reaction_ack"]:
        p["flags"].append("👍 REACTED, NEVER REPLIED")
    if p["days_silent"] is not None and p["days_silent"] >= 14 and p["creator_msgs"] == 0:
        p["flags"].append(f"❄️ COLD {int(p['days_silent'])}d")
    if p["personal"]:
        p["flags"].append("🧍 PERSONAL CONTEXT")
    if p["wins"]:
        p["flags"].append("🏆 WIN TO REINFORCE")
    if p["tier"] == "top":
        p["flags"].append("⭐ TOP VOICE")

    # --- care score (ordering only -- not shown as a number) ----------------
    if p["missed"]:
        score += 40 if wh >= 48 else (30 if wh >= 12 else 20)
    score += min(30, 15 * len(p["issues"]))
    score += min(30, 10 * len(open_qs))
    score += {"frustrated": 30, "cooling": 14}.get(p["mood"], 0)
    score += 10 * len(p["repeat_asks"])
    score += 8 * sum(1 for c in p["commitments"] if c["followed_up"])
    if p["reaction_ack"]:
        score += 8
    if p["days_silent"] is not None and p["creator_msgs"] == 0:
        if p["days_silent"] >= 30:
            score += 22
        elif p["days_silent"] >= 14:
            score += 14
    if p["tier"] == "top":
        score += 5
    p["care_score"] = score

    # --- headline: the single line a mod reads before opening the channel ----
    bits = []
    if p["missed"]:
        bits.append(f"waiting {p['waiting_human']} on us")
    if open_qs:
        topic = next((t[0] for q in open_qs for t in q["topics"]), None)
        bits.append(f"{len(open_qs)} unanswered question(s)" + (f" about {topic.lower()}" if topic else ""))
    if p["issues"]:
        bits.append(f"raised an issue ({', '.join(p['issue_tokens'][:3]) or 'see quotes'})")
    if p["mood"] in ("frustrated", "cooling"):
        bits.append(f"tone is {MOODS[p['mood']]['label'].lower()}")
    if p["repeat_asks"]:
        bits.append(f"has asked about {p['repeat_asks'][0][0].lower()} more than once")
    if not bits:
        if p["creator_msgs"] == 0 and p["days_silent"] is not None:
            bits.append(f"nothing from them in this window (last heard {int(p['days_silent'])}d ago)")
        elif p["wins"]:
            bits.append("healthy and positive -- good moment for an ask")
        else:
            bits.append("nothing outstanding -- context only")
    p["headline"] = "; ".join(bits[:3]).capitalize() + "."

    # --- handling guidance --------------------------------------------------
    h, avoid = p["handling"], p["avoid"]

    if p["mood"] == "frustrated":
        h.append("Open by owning the miss in plain language. No template, no excuses, no emoji wall.")
    elif p["mood"] == "cooling":
        h.append("Be concrete: what happened, what you are doing, and the date it lands.")
    elif p["mood"] in ("warm", "positive"):
        h.append("Rapport is good -- keep it personal and it stays that way.")

    if p["personal"]:
        h.append(f'Lead with the human note first: "{p["personal"][0][1]}"')
    if p["wins"]:
        h.append(f'Reinforce their win by name: "{p["wins"][0][1]}"')
    if open_qs:
        h.append(f"Answer the {len(open_qs)} open question(s) verbatim -- quote them back so nothing gets lost.")
    elif p["missed"]:
        h.append("Acknowledge their last message even if the answer is 'still checking' -- silence is the problem.")
    if p["issues"]:
        h.append("Name the problem, state the fix, give a date. Do not ask them to re-explain it.")
    if p["repeat_asks"]:
        h.append(
            f"They have asked about {p['repeat_asks'][0][0].lower()} in "
            f"{p['repeat_asks'][0][2]} separate messages -- close it out for good this time."
        )
    for c in p["commitments"]:
        if c["followed_up"]:
            h.append(f'We promised: "{c["text"]}" ({c["age"]} ago). Deliver it or give a new date.')
            break
    if p["style_lead"]:
        h.append("Match their format -- " + p["style_lead"] + ".")
    if p["best_window"]:
        start, end, _c = p["best_window"]
        h.append(f"They are usually around {start:02d}:00-{end:02d}:00 UTC -- reply inside that block for a same-day answer.")
    if p["creator_msgs"] == 0 and p["days_silent"] is not None and p["days_silent"] >= 14:
        h.append("Reopen with one low-effort question, not a task list. Give them an easy way back in.")

    if p["reaction_ack"]:
        avoid.append("Do not let a reaction stand in for a reply -- they cannot read an emoji as an answer.")
    if p["missed"]:
        avoid.append("Do not ask them for anything new before you answer what they already asked.")
    if p["mood"] in ("frustrated", "cooling"):
        avoid.append("Do not open with 'just checking in' -- they are the ones who have been waiting.")
    if p["issues"]:
        avoid.append("Do not close the thread until they confirm the fix actually landed.")
    if not avoid:
        avoid.append("Nothing to avoid -- just do not go silent after they reply.")

    p["handling"] = h[:7]
    p["avoid"] = avoid[:4]

    # --- draft opener (placeholders stay placeholders) -----------------------
    name = p["creator"]
    topic_hint = None
    if open_qs:
        topic_hint = next((t[0].lower() for q in open_qs for t in q["topics"]), None)
    if not topic_hint and p["topics"]:
        topic_hint = p["topics"][0][0].lower()
    subject = topic_hint or "{{their open item}}"

    if p["issues"] and p["missed"]:
        p["opener"] = (
            f"Hey {name} — that's on us, you shouldn't have had to wait {p['waiting_human']} on this. "
            f"On the {subject} issue: {{{{what actually happened}}}}. "
            f"Here's the fix: {{{{action}}}} by {{{{date}}}}. I'll confirm here the moment it's done."
        )
    elif p["missed"]:
        p["opener"] = (
            f"Hey {name} — thanks for your patience, and sorry for the wait. "
            f"To your question on {subject}: {{{{answer}}}}. "
            f"Anything else open on your side?"
        )
    elif p["creator_msgs"] == 0 and p["days_silent"] is not None and p["days_silent"] >= 14:
        p["opener"] = (
            f"Hey {name} — checking in, no ask attached. "
            f"Last we talked it was {subject}. {{{{one specific, easy question}}}}"
        )
    elif p["wins"]:
        p["opener"] = (
            f"Hey {name} — saw {{{{their win, quoted from the card above}}}}, that's great. "
            f"Quick one on {subject}: {{{{update}}}}."
        )
    else:
        p["opener"] = (
            f"Hey {name} — quick update on {subject}: {{{{update}}}}. "
            f"Nothing needed from you unless {{{{condition}}}}."
        )


# ---------------------------------------------------------------------------
# Group roll-up
# ---------------------------------------------------------------------------

def build_group_care(scan: dict) -> dict:
    """Profile every channel in a scan and roll it up. Cached on the scan dict."""
    if scan.get("care"):
        return scan["care"]

    now = scan["now"]
    profiles = [profile_channel(r, now) for r in scan["results"]]

    # Engagement tier is relative to this group, so it needs every profile first.
    live = [p for p in profiles if p["bucket"] != "XX"]
    volumes = sorted((p["creator_msgs"] for p in live), reverse=True)
    top_cut = volumes[max(0, len(volumes) // 4 - 1)] if volumes else 0
    median_vol = _median([p["creator_msgs"] for p in live]) or 0
    for p in live:
        if p["creator_msgs"] == 0:
            p["tier"] = "silent"
        elif p["creator_msgs"] >= max(3, top_cut):
            p["tier"] = "top"
        elif p["creator_msgs"] >= median_vol:
            p["tier"] = "steady"
        else:
            p["tier"] = "light"

    for p in profiles:
        _finalize_profile(p, now)

    ordered = sorted(
        profiles,
        key=lambda p: (
            0 if p["bucket"] != "XX" else 1,
            -p["care_score"],
            MOODS[p["mood"]]["order"],
            p["creator"].lower(),
        ),
    )

    # --- aggregates ---------------------------------------------------------
    topics: Dict[str, dict] = {}
    for p in live:
        for name, emoji, hits in p["topics"]:
            slot = topics.setdefault(name, {"emoji": emoji, "msgs": 0, "creators": []})
            slot["msgs"] += hits
            slot["creators"].append(p["creator"])
    top_topics = sorted(topics.items(), key=lambda kv: kv[1]["msgs"], reverse=True)

    issue_tokens: Dict[str, List[str]] = {}
    for p in live:
        for tok in p["issue_tokens"]:
            issue_tokens.setdefault(tok, [])
            if p["creator"] not in issue_tokens[tok]:
                issue_tokens[tok].append(p["creator"])
    top_issues = sorted(issue_tokens.items(), key=lambda kv: len(kv[1]), reverse=True)

    # Questions grouped by topic across creators -> what the whole group is confused about.
    ask_map: Dict[str, dict] = {}
    for p in live:
        for q in p["questions"]:
            for name, emoji in q["topics"]:
                slot = ask_map.setdefault(name, {"emoji": emoji, "creators": [], "asks": 0, "examples": []})
                slot["asks"] += 1
                if p["creator"] not in slot["creators"]:
                    slot["creators"].append(p["creator"])
                if len(slot["examples"]) < 3:
                    slot["examples"].append((p["creator"], q["text"]))
    recurring = sorted(
        [(n, v) for n, v in ask_map.items() if len(v["creators"]) >= 2],
        key=lambda kv: (len(kv[1]["creators"]), kv[1]["asks"]), reverse=True,
    )

    moods = {key: 0 for key in MOODS}
    for p in live:
        moods[p["mood"]] += 1

    all_deltas = []
    for p in live:
        if p["reply_median"] is not None:
            all_deltas.append(p["reply_median"])

    at_risk = [
        p for p in ordered
        if p["bucket"] != "XX" and (
            p["mood"] in ("frustrated", "cooling")
            or (p["days_silent"] is not None and p["days_silent"] >= 21)
            or (p["waiting_hours"] or 0) >= 48
        )
    ]

    care = {
        "profiles":    ordered,
        "live":        live,
        "top_topics":  top_topics,
        "top_issues":  top_issues,
        "recurring":   recurring,
        "moods":       moods,
        "reply_median_group": _median(all_deltas),
        "reply_channels":     len(all_deltas),
        "reply_samples":      sum(p["reply_samples"] for p in live),
        "at_risk":     at_risk,
        "wins":        [p for p in live if p["wins"]],
        "personal":    [p for p in live if p["personal"]],
        "promises":    [p for p in live if any(c["followed_up"] for c in p["commitments"])],
        "cold":        [p for p in live if p["days_silent"] is not None and p["days_silent"] >= 14 and p["creator_msgs"] == 0],
    }
    scan["care"] = care
    return care


# ---------------------------------------------------------------------------
# Care Brief text file
# ---------------------------------------------------------------------------

def _sub(title: str) -> str:
    body = f"  ── {title} "
    return body + "─" * max(4, 94 - len(body))


def _bar(n: int, cap: int = 24) -> str:
    return "#" * min(max(n, 0), cap)


def build_care_report_text(scan: dict, requester: str) -> str:
    care = build_group_care(scan)
    group = scan["group"]
    tf = engine.TIMEFRAMES[scan["timeframe"]]
    now, since = scan["now"], scan["since"]
    t = scan["totals"]
    profiles = care["profiles"]
    live = care["live"]

    L: List[str] = []
    add = L.append

    # ================= header =================
    add(WIDE)
    add(f"  TRUE CLASSIC  -  {group['label'].upper()}  -  CREATOR CARE BRIEF")
    add(WIDE)
    add("  A quick-reference card per creator, built for personalised customer care.")
    add("  Read the card before you open the channel -- everything quoted here is something")
    add("  the creator actually typed, so you can reference it word for word.")
    add(THIN)
    add(f"  Group ............. {group['label']}  ({t['channels']} channels)")
    add(f"  Window ............ {tf['long']}   [{since.strftime('%Y-%m-%d %H:%M')} -> {now.strftime('%Y-%m-%d %H:%M')} UTC]")
    add(f"  Generated ......... {now.strftime('%Y-%m-%d %H:%M UTC')}   by {requester}")
    add(f"  Cards ............. {len(profiles)}  (ordered by who needs the most care first)")
    add(THIN)
    add("  CONTENTS")
    add("    1  CARE QUEUE ............ who to touch first and why")
    add("    2  GROUP PULSE ........... mood, volume, our response speed")
    add("    3  WHAT THE GROUP TALKS ABOUT")
    add("    4  ASKED BY MULTIPLE CREATORS  ..... fix these once, publicly")
    add("    5  WATCHLIST ............. at risk, going cold, promises owed")
    add("    6  CREATOR CARE CARDS .... one per channel")
    add("    7  HOW TO USE THIS BRIEF")
    add(WIDE)
    add("")

    # ================= 1. care queue =================
    add("  1  CARE QUEUE")
    add(_sub("who needs a human first -- work top down, card numbers match section 6"))
    for i, p in enumerate(profiles, start=1):
        mood = MOODS[p["mood"]]
        waiting = f"waiting {p['waiting_human']}" if p["waiting_human"] else ""
        add(f"  {i:>2}. {mood['emoji']} {p['creator'][:26]:<26} #{p['channel_name'][:26]:<26} {waiting}".rstrip())
        for line in _wrap_text("      └ ", p["headline"], hang="        "):
            add(line)
        for line in _wrap_parts("        ", p["flags"][:6]):
            add(line)
        add("")
    add("  Legend: 😠 unhappy  😕 patience thin  😐 neutral  🙂 warm  😄 positive  🔇 said nothing")
    add(WIDE)
    add("")

    # ================= 2. group pulse =================
    add("  2  GROUP PULSE")
    add(_sub("the temperature of the whole group"))
    add(f"  Messages in window ....... {t['messages']}  (creators {t['creator_msgs']} | staff {t['staff_msgs']} | bot {t['bot_msgs']})")
    add(f"  Channels with activity ... {t['active']} / {t['channels']}")
    add(f"  Creators waiting on us ... {sum(1 for p in live if p['missed'])}  ({t['unreplied']} unanswered message(s))")
    add(f"  Open questions ........... {sum(len(p.get('open_questions') or []) for p in live)}")
    add("")
    add("  MOOD SPREAD (creators, this window)")
    for key in ["frustrated", "cooling", "neutral", "warm", "positive", "nosignal"]:
        cnt = care["moods"].get(key, 0)
        if cnt:
            m = MOODS[key]
            add(f"    {m['emoji']} {m['label']:<12} {cnt:>3}  {_bar(cnt)}")
    add("")
    if care["reply_median_group"] is not None:
        L.extend(_wrap_text(
            "  OUR RESPONSE SPEED ....... ",
            f"typical first reply {humanize(care['reply_median_group'])} "
            f"(median of {care['reply_channels']} channel(s) where we answered, "
            f"{care['reply_samples']} reply pair(s))",
        ))
        slowest = max(
            (p for p in live if p["reply_slowest"] is not None),
            key=lambda p: p["reply_slowest"], default=None,
        )
        if slowest:
            add(f"  SLOWEST SINGLE REPLY ..... {humanize(slowest['reply_slowest'])} in #{slowest['channel_name']}")
    else:
        add("  OUR RESPONSE SPEED ....... no creator message was answered inside this window")
    add(WIDE)
    add("")

    # ================= 3. topics =================
    add("  3  WHAT THE GROUP TALKS ABOUT")
    add(_sub("most common topics -- messages mentioning each, and how many creators"))
    if care["top_topics"]:
        for name, v in care["top_topics"][:12]:
            add(f"    {v['emoji']} {name:<26} {v['msgs']:>4} msg   {len(v['creators']):>2} creator(s)  {_bar(v['msgs'])}")
        add("")
        head = care["top_topics"][0]
        L.extend(_wrap_text(
            "  ▸ ",
            f"Dominant theme is {head[0]} ({head[1]['msgs']} messages across "
            f"{len(head[1]['creators'])} creator(s)). If you only prep one thing before your "
            "shift, prep that.",
            hang="    ",
        ))
    else:
        add("    No topic keywords matched in this window.")
    add("")
    if care["top_issues"]:
        add(_sub("problem words creators used (grouped by how many creators used them)"))
        for tok, creators in care["top_issues"][:10]:
            label = f'"{tok}"'
            L.extend(_wrap_text(
                f"    ⚠️ {label:<22} {len(creators)} creator(s): ",
                f"{', '.join(creators[:6])}{' …' if len(creators) > 6 else ''}",
                hang="       ",
            ))
        add("")
        add("  ▸ A word used by 3+ creators is usually a process problem, not a person problem.")
        add("    Fix it upstream instead of answering it 3 times.")
    else:
        add(_sub("problem words creators used"))
        add("    None detected. Good window.")
    add(WIDE)
    add("")

    # ================= 4. recurring asks =================
    add("  4  ASKED BY MULTIPLE CREATORS")
    add(_sub("answer these once in a pinned post / FAQ and the DMs get quieter"))
    if care["recurring"]:
        for name, v in care["recurring"][:8]:
            add(f"    {v['emoji']} {name}  --  {len(v['creators'])} creator(s), {v['asks']} question(s)")
            L.extend(_wrap_text(
                "       who: ",
                f"{', '.join(v['creators'][:6])}{' …' if len(v['creators']) > 6 else ''}",
                hang="            ",
            ))
            for who, text in v["examples"][:2]:
                L.extend(_wrap_text(f"       e.g. {who}: ", f'"{text}"', hang="            "))
            add("")
    else:
        add("    Nothing was asked by two or more creators in this window.")
        add("")
    add(WIDE)
    add("")

    # ================= 5. watchlist =================
    add("  5  WATCHLIST")
    add(_sub("relationships that need attention beyond a single reply"))

    def _list(title: str, items: List[dict], render) -> None:
        add(f"  {title} ({len(items)})")
        if not items:
            add("     none")
        else:
            for p in items[:12]:
                add(f"     • {render(p)}")
        add("")

    _list("AT RISK -- unhappy, waiting 48h+, or gone quiet 21d+", care["at_risk"],
          lambda p: f"{p['creator']:<22} {MOODS[p['mood']]['emoji']} {_clip(p['headline'], 56)}")
    _list("GOING COLD -- silent 14d+ and nothing in this window", care["cold"],
          lambda p: f"{p['creator']:<22} last heard {int(p['days_silent'])}d ago")
    _list("PROMISES WE OWE -- we committed and they came back after", care["promises"],
          lambda p: f"{p['creator']:<22} \"{_clip(next(c['text'] for c in p['commitments'] if c['followed_up']), 52)}\"")
    _list("WINS TO REINFORCE -- thank these people by name today", care["wins"],
          lambda p: f"{p['creator']:<22} \"{_clip(p['wins'][0][1], 52)}\"")
    _list("PERSONAL NOTES ON FILE -- open with this, not with business", care["personal"],
          lambda p: f"{p['creator']:<22} \"{_clip(p['personal'][0][1], 52)}\"")
    add(WIDE)
    add("")
    add("")

    # ================= 6. cards =================
    add("  6  CREATOR CARE CARDS")
    add("")
    total = len(profiles)
    for idx, p in enumerate(profiles, start=1):
        mood = MOODS[p["mood"]]
        tier = TIERS[p["tier"]]
        bucket = engine.BUCKETS[p["bucket"]]

        add(HASH)
        add(f"  CARE CARD {idx:02d}/{total:02d}   -   {p['creator']}   -   #{p['channel_name']}")
        add(HASH)

        if p["bucket"] == "XX":
            add(f"  STATUS ......... 🚫 UNREADABLE -- {p['error']}")
            add(f"  CHANNEL ID ..... {p['channel_id']}")
            add("  FIX ............ Give the bot View Channel + Read Message History here, or update")
            add("                   the roster in core/inner_groups.py if the channel moved.")
            add("")
            add("")
            continue

        add(f"  STATUS ......... {bucket['emoji']} {bucket['label']}   |   "
            f"MOOD {mood['emoji']} {mood['label']}   |   VOLUME {tier['emoji']} {tier['label']}")
        for line in _wrap_parts("  FLAGS .......... ", p["flags"]):
            add(line)
        for line in _wrap_text("  READ THIS ...... ", p["headline"]):
            add(line)
        for line in _wrap_text("  TONE NOTE ...... ", mood["note"]):
            add(line)
        add("")

        # -- quick facts
        add(_sub("QUICK FACTS"))
        c = p["counts"]
        add(f"    Messages (window) ... {c['total']}  (creator {c['creator']} | staff {c['staff']} | bot {c['bot']})")
        if p["last_creator"]:
            stamp, ago, author, _prev = p["last_creator"]
            add(f"    Last heard from ..... {stamp}  ({ago} ago)")
        elif p["last_msg"]:
            stamp, cls, author, _prev = p["last_msg"]
            add(f"    Last activity ....... {stamp}  by {author} ({cls.upper()})")
        if p["days_silent"] is not None and (c["total"] == 0 or p["days_silent"] >= 3):
            add(f"    Channel quiet for ... {p['days_silent']:.1f} day(s) since the newest message")
        if p["last_staff"]:
            stamp, ago, author, _prev = p["last_staff"]
            add(f"    Our last reply ...... {stamp}  ({ago} ago, {author})")
        else:
            add("    Our last reply ...... none in this window")
        if p["reply_median"] is not None:
            plural = "reply" if p["reply_samples"] == 1 else "replies"
            add(f"    Our reply speed ..... typical {humanize(p['reply_median'])}  |  "
                f"slowest {humanize(p['reply_slowest'])}  (from {p['reply_samples']} {plural})")
        else:
            add("    Our reply speed ..... no creator message was answered inside this window")
        if p["best_window"]:
            start, end, cnt = p["best_window"]
            days = f"  •  most active {' / '.join(p['best_days'])}" if p["best_days"] else ""
            add(f"    Best time to reach .. {start:02d}:00-{end:02d}:00 UTC ({cnt} of their messages){days}")
        if p["style"]:
            L.extend(_wrap_text("    How they write ...... ", "; ".join(p["style"])))
        add("")

        # -- topics
        if p["topics"]:
            add(_sub("WHAT THEY TALK ABOUT MOST"))
            for name, emoji, hits in p["topics"][:8]:
                add(f"    {emoji} {name:<26} {hits:>3} msg  {_bar(hits, 18)}")
            add("")

        if p["repeat_asks"]:
            add(_sub("THEY HAVE ASKED MORE THAN ONCE"))
            for name, emoji, cnt in p["repeat_asks"]:
                add(f"    🔁 {emoji} {name:<26} asked in {cnt} separate message(s)")
            add("    ▸ Repeat asks mean our earlier answer did not land. Close it for good this time.")
            add("")

        # -- missed
        if p["missed"]:
            add(_sub("MESSAGES WE MISSED (verbatim, oldest first)"))
            for i, (stamp, ago, text) in enumerate(p["missed"], start=1):
                L.extend(_wrap_text(f"    {i}. [{stamp} • {ago} ago] ", f'"{text}"', hang="       "))
            add("")

        open_qs = p.get("open_questions") or []
        if open_qs:
            add(_sub("OPEN QUESTIONS -- answer these explicitly"))
            for i, q in enumerate(open_qs, start=1):
                tags = ", ".join(n for n, _e in q["topics"]) or "general"
                L.extend(_wrap_text(f"    {i}. [{q['stamp']}] ", f'"{q["text"]}"', hang="       "))
                add(f"       └ topic: {tags}")
            add("")

        answered_qs = [q for q in p["questions"] if q["answered"]]
        if answered_qs and not open_qs:
            add(_sub("WHAT THEY ASKED THIS WINDOW (already answered -- context)"))
            for q in answered_qs[:4]:
                L.extend(_wrap_text(f"    • [{q['stamp']}] ", f'"{q["text"]}"', hang="      "))
            add("")

        if p["issues"]:
            add(_sub("ISSUES THEY RAISED (their words)"))
            for stamp, text in p["issues"]:
                L.extend(_wrap_text(f"    ⚠️ [{stamp}] ", f'"{text}"', hang="       "))
            if p["issue_tokens"]:
                L.extend(_wrap_text("    ▸ trigger words: ", ", ".join(p["issue_tokens"][:6]), hang="      "))
            add("")

        if p["commitments"]:
            add(_sub("WHAT WE PROMISED THEM"))
            for c in p["commitments"]:
                mark = "🔴 they came back after this" if c["followed_up"] else "⚪ no follow-up from them yet"
                L.extend(_wrap_text(
                    f"    [{c['stamp']} • {c['age']} ago] {c['author']}: ", f'"{c["text"]}"', hang="       "
                ))
                add(f"       └ {mark}")
            add("    ▸ Detected from our own wording -- confirm it actually shipped before you re-promise.")
            add("")

        if p["personal"]:
            add(_sub("PERSONAL CONTEXT -- use it, do not ignore it"))
            for stamp, text in p["personal"]:
                L.extend(_wrap_text(f"    🧍 [{stamp}] ", f'"{text}"', hang="       "))
            add("    ▸ This is the difference between a support ticket and a relationship.")
            add("")

        if p["wins"]:
            add(_sub("WINS TO REINFORCE"))
            for stamp, text in p["wins"]:
                L.extend(_wrap_text(f"    🏆 [{stamp}] ", f'"{text}"', hang="       "))
            add("    ▸ Name the win in your reply. Specific praise beats generic praise every time.")
            add("")

        add(_sub("HOW TO HANDLE THIS CREATOR"))
        for i, line in enumerate(p["handling"], start=1):
            L.extend(_wrap_text(f"    {i}. ", line, hang="       "))
        add("")
        add("    AVOID")
        for line in p["avoid"]:
            L.extend(_wrap_text("      ✗ ", line, hang="        "))
        add("")

        add(_sub("DRAFT OPENER -- edit before sending, fill every {{placeholder}}"))
        for line in _wrap_text('    "', p["opener"] + '"', hang="     "):
            add(line)
        add("")

        if p["next_steps"]:
            add(_sub("TRIAGE NEXT STEPS (from the summary report)"))
            for i, step in enumerate(p["next_steps"][:4], start=1):
                L.extend(_wrap_text(f"    {i}. ", step, hang="       "))
            add("")
        add("")

    # ================= 7. how to use =================
    add(WIDE)
    add("  7  HOW TO USE THIS BRIEF")
    add(THIN)
    add("  1. Work the CARE QUEUE top down. Card 01 is the person most likely to churn today.")
    add("  2. Read the card fully before you type. The quotes are there so your reply can")
    add("     reference their exact words -- that is what makes it feel personal.")
    add("  3. Answer open questions verbatim, then handle the issue, then be human. In that order")
    add("     for anyone unhappy; reverse it for anyone warm.")
    add("  4. Never send the DRAFT OPENER as-is. Every {{placeholder}} is a fact only you have.")
    add("  5. Anything under ASKED BY MULTIPLE CREATORS belongs in a pinned post or FAQ, not in")
    add("     five separate DMs.")
    add("  6. After you reply, post the outcome in-channel so the next mod inherits the context")
    add("     and the next brief reads clean.")
    add("")
    add("  Mood, topics, promises and repeat asks are detected from message text with a fixed")
    add("  keyword model -- no AI guesswork, same input always gives the same brief. It is a")
    add("  preparation aid: the conversation itself is still the source of truth.")
    add(WIDE)
    add(f"  END OF CARE BRIEF  -  {group['label']}  -  {tf['long']}  -  {now.strftime('%Y-%m-%d %H:%M UTC')}")
    add(f"  True Classic Community Operations Bot  -  requested by {requester}")
    add(WIDE)

    return "\n".join(L)


def care_filename(scan: dict) -> str:
    group = scan["group"]
    stamp = scan["now"].strftime("%Y-%m-%d_%H%M")
    return f"{group['slug']}_care_brief_{scan['timeframe']}_{stamp}.txt"
