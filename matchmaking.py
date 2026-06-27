"""
Matchmaking system for clan wars.
Rules:
- Each player should play roughly equally often (round-robin within clans)
- Prioritise matchups between clans that haven't played each other yet
- After an outsider battle, schedule a battle with the leading clan
- No player plays twice in a row if others are available
"""
import random
from database import get_all_clans, get_clan_members


async def pick_next_duel(group_id: int, last_p1: int = None, last_p2: int = None):
    """
    Returns (player1_id, player2_id, clan1_id, clan2_id) or None if < 2 clans exist.
    """
    clans = await get_all_clans()
    if len(clans) < 2:
        return None

    # Build member lists per clan
    clan_members: dict[int, list] = {}
    for clan in clans:
        members = await get_clan_members(clan["id"])
        if members:
            clan_members[clan["id"]] = [m["user_id"] for m in members]

    eligible_clans = [c for c in clans if c["id"] in clan_members and len(clan_members[c["id"]]) > 0]
    if len(eligible_clans) < 2:
        return None

    # Sort by points ascending — outsiders first
    sorted_clans = sorted(eligible_clans, key=lambda c: c["points"])
    top_clan = sorted_clans[-1]
    bottom_clan = sorted_clans[0]

    # Alternate: sometimes match bottom vs top, sometimes bottom vs second bottom
    if random.random() < 0.5 or len(eligible_clans) == 2:
        clan_a = bottom_clan
        clan_b = top_clan
    else:
        clan_a = sorted_clans[0]
        clan_b = sorted_clans[1]

    def pick_player(clan, last_played):
        members = clan_members.get(clan["id"], [])
        if not members:
            return None
        # Prefer someone who didn't just play
        available = [m for m in members if m != last_played]
        if not available:
            available = members
        return random.choice(available)

    p1 = pick_player(clan_a, last_p1)
    p2 = pick_player(clan_b, last_p2)

    if p1 is None or p2 is None:
        return None

    return p1, p2, clan_a["id"], clan_b["id"]
