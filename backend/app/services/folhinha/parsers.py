"""Parse FolhinhaBot commands and reply patterns into structured events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal[
    "bonk",
    "abraco",
    "roulette_survive",
    "roulette_death",
    "cookie_cd",
    "cookie_claim",
    "cookie_balance",
    "cookie_slot",
]

# User-issued commands
USER_BONK = re.compile(r"^\s*\?bonk\s+(?P<target>\S+)", re.IGNORECASE)
USER_ABRACO = re.compile(r"^\s*\?abra[cç]o\s+(?P<target>\S+)", re.IGNORECASE)
USER_ROULETTE = re.compile(r"^\s*\?(?P<cmd>rr|roleta)\b", re.IGNORECASE)
USER_CD = re.compile(r"^\s*\?cd\b", re.IGNORECASE)
USER_COOKIE_SLOT = re.compile(
    r"^\s*\?(?:cookie|c)\s+slot\b",
    re.IGNORECASE,
)

# Folhinha replies
MENTION = re.compile(r"^@(?P<user>\w+)\s+", re.IGNORECASE)
ROULETTE_CLICK = re.compile(
    r"^@(?P<user>\w+)\s+Click!\s+Não foi dessa vez",
    re.IGNORECASE,
)
ROULETTE_BANG = re.compile(r"^\s*BANG!", re.IGNORECASE)

PCT = re.compile(r"(?P<pct>\d{1,3}(?:\.\d+)?)\s*%")
BONK_TARGET_HINT = re.compile(
    r"(?:\bem|no|na|em\s+cima\s+d[eo]|contra)\s+@?(?P<target>[\w]+)"
    r"|@(?P<target_at>[\w]+)\s*$",
    re.IGNORECASE,
)

# Real Folhinha bonk replies (community CSV):
#   @User User deu um bonk com impacto de 64% em Target BOP
#   @User User deu um bonk com impacto de 96% e nocauteou Target
#   @User User tentou bonkar Target mas acabou se auto-nocauteando (impacto de 0%)
BONK_IMPACTO = re.compile(
    r"^@(?P<ping>\w+)\s+"
    r"(?P<actor>\w+)\s+deu um bonk com impacto de\s+(?P<pct>\d+(?:\.\d+)?)%\s+"
    r"(?:e nocauteou|em)\s+(?P<target>[\w]+)",
    re.IGNORECASE,
)
BONK_SELF_FAIL = re.compile(
    r"^@(?P<ping>\w+)\s+"
    r"(?P<actor>\w+)\s+tentou bonkar\s+(?P<target>[\w]+)\s+.+?"
    r"impacto de\s+(?P<pct>\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
BONK_IGNORE = re.compile(
    r"se bonkar|Por que você me bateu\?|Use o formato:\s*\?bonk",
    re.IGNORECASE,
)

ABRACO_REPLY = re.compile(
    r"^@(?P<actor>\w+)\s+.+?(?:abra[cç]o|abraçou|hug)",
    re.IGNORECASE,
)

COOKIE_CLAIM = re.compile(
    r"^@(?P<user>\w+)\s+Você resgatou seu .+?agora tem\s+(?P<balance>\d+)\s+cookies?",
    re.IGNORECASE,
)
COOKIE_STATUS = re.compile(
    r"^@(?P<ping>\w+)\s+(?P<name>\w+)\s+tem\s+(?P<balance>\d+)\s+cookies?",
    re.IGNORECASE,
)
COOKIE_SLOT = re.compile(
    r"^@(?P<user>\w+)\s+\[[^\]]+\]\s+você apostou\s+(?P<wager>\d+)\s+cookie",
    re.IGNORECASE,
)
COOKIE_SLOT_DELTA = re.compile(
    r"\[(?P<delta>[+-]?\d+)\s*⇒\s*(?P<balance>\d+)\]",
)


@dataclass
class ParsedEvent:
    kind: Kind
    actor_username: str | None = None
    target_username: str | None = None
    percentage: float | None = None
    command: str | None = None
    confidence: str = "high"
    cookies_balance: int | None = None
    cookies_delta: int | None = None
    cookies_wagered: int | None = None


def _norm_login(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lstrip("@").lower()
    cleaned = cleaned.rstrip(".,!?;:")
    return cleaned or None


def _resolve_target(raw: str | None, actor: str | None) -> str | None:
    target = _norm_login(raw)
    if not target:
        return None
    if target in {"todos", "all", "everyone", "chat", "todo_mundo"}:
        return None
    if target in {"eu", "me", "myself"}:
        return actor
    return target


def parse_user_command(
    message: str,
    *,
    username: str,
) -> ParsedEvent | None:
    """Parse a chatter's Folhinha commands."""
    text = (message or "").strip()
    actor = _norm_login(username)
    if not actor or not text:
        return None

    if USER_CD.match(text):
        return ParsedEvent(
            kind="cookie_cd",
            actor_username=actor,
            command="?cd",
            confidence="high",
        )

    if USER_COOKIE_SLOT.match(text):
        return ParsedEvent(
            kind="cookie_slot",
            actor_username=actor,
            command="?cookie slot",
            confidence="medium",
        )

    m = USER_BONK.match(text)
    if m:
        return ParsedEvent(
            kind="bonk",
            actor_username=actor,
            target_username=_resolve_target(m.group("target"), actor),
            percentage=None,
            command="?bonk",
            confidence="high",
        )

    m = USER_ABRACO.match(text)
    if m:
        cmd = text.split()[0].lower()
        if not cmd.startswith("?"):
            cmd = "?abraco"
        return ParsedEvent(
            kind="abraco",
            actor_username=actor,
            target_username=_resolve_target(m.group("target"), actor),
            percentage=None,
            command=cmd[:16],
            confidence="high",
        )

    if USER_ROULETTE.match(text):
        return None

    return None


def parse_folhinha_reply(message: str) -> ParsedEvent | None:
    """Parse FolhinhaBot chat replies into events."""
    text = (message or "").strip()
    if not text:
        return None

    m = ROULETTE_CLICK.match(text)
    if m:
        return ParsedEvent(
            kind="roulette_survive",
            actor_username=_norm_login(m.group("user")),
            command="?rr",
            confidence="high",
        )

    if ROULETTE_BANG.match(text):
        return ParsedEvent(
            kind="roulette_death",
            actor_username=None,
            command="?rr",
            confidence="low",
        )

    m = COOKIE_CLAIM.match(text)
    if m:
        return ParsedEvent(
            kind="cookie_claim",
            actor_username=_norm_login(m.group("user")),
            command="?cd",
            cookies_balance=int(m.group("balance")),
            confidence="high",
        )

    m = COOKIE_SLOT.match(text)
    if m:
        delta_m = COOKIE_SLOT_DELTA.search(text)
        delta = int(delta_m.group("delta")) if delta_m else None
        balance = int(delta_m.group("balance")) if delta_m else None
        if delta is None:
            if re.search(r"ganhou\s+\d+", text, re.I):
                won = re.search(r"ganhou\s+(\d+)", text, re.I)
                wager = int(m.group("wager"))
                if won:
                    delta = int(won.group(1)) - wager
            elif re.search(r"ficou sem", text, re.I):
                delta = -int(m.group("wager"))
        return ParsedEvent(
            kind="cookie_slot",
            actor_username=_norm_login(m.group("user")),
            command="?cookie slot",
            cookies_wagered=int(m.group("wager")),
            cookies_delta=delta,
            cookies_balance=balance,
            confidence="high" if delta is not None else "medium",
        )

    m = COOKIE_STATUS.match(text)
    if m:
        actor = _norm_login(m.group("name")) or _norm_login(m.group("ping"))
        return ParsedEvent(
            kind="cookie_balance",
            actor_username=actor,
            command="?cookie",
            cookies_balance=int(m.group("balance")),
            confidence="high",
        )

    if BONK_IGNORE.search(text):
        return None

    m = BONK_IMPACTO.match(text)
    if m:
        actor = _norm_login(m.group("actor")) or _norm_login(m.group("ping"))
        target = _resolve_target(m.group("target"), actor)
        pct = min(float(m.group("pct")), 100.0)
        return ParsedEvent(
            kind="bonk",
            actor_username=actor,
            target_username=target,
            percentage=pct,
            command="?bonk",
            confidence="high" if target else "medium",
        )

    m = BONK_SELF_FAIL.match(text)
    if m:
        actor = _norm_login(m.group("actor")) or _norm_login(m.group("ping"))
        target = _resolve_target(m.group("target"), actor)
        pct = min(float(m.group("pct")), 100.0)
        return ParsedEvent(
            kind="bonk",
            actor_username=actor,
            target_username=target,
            percentage=pct,
            command="?bonk",
            confidence="high",
        )

    pct_m = PCT.search(text)
    mention = MENTION.match(text)
    if (
        pct_m
        and mention
        and ("bonk" in text.lower() or "impacto" in text.lower() or "mrdestructoid" in text.lower())
    ):
        actor = _norm_login(mention.group("user"))
        pct = min(float(pct_m.group("pct")), 100.0)
        target = None
        th = BONK_TARGET_HINT.search(text)
        if th:
            target = _norm_login(th.group("target") or th.group("target_at"))
        return ParsedEvent(
            kind="bonk",
            actor_username=actor,
            target_username=target,
            percentage=pct,
            command="?bonk",
            confidence="high" if target else "medium",
        )

    m = ABRACO_REPLY.match(text)
    if m:
        return ParsedEvent(
            kind="abraco",
            actor_username=_norm_login(m.group("actor")),
            target_username=None,
            command="?abraco",
            confidence="low",
        )

    return None
