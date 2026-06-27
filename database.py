import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "clanwar.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                motto TEXT,
                avatar_file_id TEXT,
                creator_id INTEGER NOT NULL,
                points REAL DEFAULT 100,
                wins INTEGER DEFAULT 0,
                max_win_streak INTEGER DEFAULT 0,
                current_win_streak INTEGER DEFAULT 0,
                max_multiplier REAL DEFAULT 0,
                max_multiplier_user TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                clan_id INTEGER,
                FOREIGN KEY (clan_id) REFERENCES clans(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER NOT NULL,
                clan1_id INTEGER NOT NULL,
                clan2_id INTEGER NOT NULL,
                state TEXT DEFAULT 'pending',
                current_player INTEGER,
                mines_count INTEGER DEFAULT 0,
                bet_multiplier REAL DEFAULT 1.0,
                current_multiplier REAL DEFAULT 1.0,
                opened_cells TEXT DEFAULT '',
                mine_positions TEXT DEFAULT '',
                message_id INTEGER,
                field_message_id INTEGER,
                p1_done INTEGER DEFAULT 0,
                p2_done INTEGER DEFAULT 0,
                p1_result REAL DEFAULT 0,
                p2_result REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS war_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                start_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_date DATETIME,
                active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duel_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                next_duel_time DATETIME,
                last_p1_id INTEGER,
                last_p2_id INTEGER
            )
        """)
        await db.commit()

# ─── CLAN ───────────────────────────────────────────────────────────────────

async def create_clan(name: str, motto: str, avatar_file_id: str, creator_id: int, creator_username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO clans (name, motto, avatar_file_id, creator_id) VALUES (?,?,?,?)",
            (name, motto, avatar_file_id, creator_id)
        )
        clan_id = cur.lastrowid
        await db.execute(
            "INSERT OR REPLACE INTO members (user_id, username, clan_id) VALUES (?,?,?)",
            (creator_id, creator_username, clan_id)
        )
        await db.commit()
        return clan_id

async def get_clan_by_id(clan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clans WHERE id=?", (clan_id,))
        return await cur.fetchone()

async def get_clan_by_name(name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clans WHERE name=?", (name,))
        return await cur.fetchone()

async def get_all_clans():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clans ORDER BY points DESC")
        return await cur.fetchall()

async def get_user_clan(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT c.* FROM clans c JOIN members m ON c.id=m.clan_id WHERE m.user_id=?",
            (user_id,)
        )
        return await cur.fetchone()

async def join_clan(user_id: int, username: str, clan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO members (user_id, username, clan_id) VALUES (?,?,?)",
            (user_id, username, clan_id)
        )
        await db.commit()

async def get_clan_members(clan_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM members WHERE clan_id=?",
            (clan_id,)
        )
        return await cur.fetchall()

async def update_clan_points(clan_id: int, new_points: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE clans SET points=? WHERE id=?", (new_points, clan_id))
        await db.commit()

async def update_clan_stats(clan_id: int, won: bool, multiplier: float = 0, winner_name: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clans WHERE id=?", (clan_id,))
        clan = await cur.fetchone()
        if not clan:
            return
        new_streak = clan["current_win_streak"] + 1 if won else 0
        max_streak = max(clan["max_win_streak"], new_streak)
        wins = clan["wins"] + (1 if won else 0)
        max_mult = clan["max_multiplier"]
        max_mult_user = clan["max_multiplier_user"]
        if multiplier > max_mult:
            max_mult = multiplier
            max_mult_user = winner_name
        await db.execute(
            "UPDATE clans SET wins=?, current_win_streak=?, max_win_streak=?, max_multiplier=?, max_multiplier_user=? WHERE id=?",
            (wins, new_streak, max_streak, max_mult, max_mult_user, clan_id)
        )
        await db.commit()

# ─── DUEL ───────────────────────────────────────────────────────────────────

async def create_duel(group_id, p1_id, p2_id, clan1_id, clan2_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO duels (group_id, player1_id, player2_id, clan1_id, clan2_id, current_player, state)
               VALUES (?,?,?,?,?,?,?)""",
            (group_id, p1_id, p2_id, clan1_id, clan2_id, p1_id, 'waiting_bet')
        )
        await db.commit()
        return cur.lastrowid

async def get_duel(duel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM duels WHERE id=?", (duel_id,))
        return await cur.fetchone()

async def get_active_duel_for_player(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM duels WHERE (player1_id=? OR player2_id=?) 
               AND state NOT IN ('finished','cancelled') ORDER BY id DESC LIMIT 1""",
            (user_id, user_id)
        )
        return await cur.fetchone()

async def get_active_duel_for_group(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM duels WHERE group_id=? AND state NOT IN ('finished','cancelled') ORDER BY id DESC LIMIT 1",
            (group_id,)
        )
        return await cur.fetchone()

async def update_duel(duel_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [duel_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE duels SET {sets} WHERE id=?", vals)
        await db.commit()

# ─── QUEUE ──────────────────────────────────────────────────────────────────

async def get_queue(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM duel_queue WHERE group_id=?", (group_id,))
        return await cur.fetchone()

async def set_queue(group_id: int, next_time: str, p1_id: int, p2_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await (await db.execute("SELECT id FROM duel_queue WHERE group_id=?", (group_id,))).fetchone()
        if existing:
            await db.execute(
                "UPDATE duel_queue SET next_duel_time=?, last_p1_id=?, last_p2_id=? WHERE group_id=?",
                (next_time, p1_id, p2_id, group_id)
            )
        else:
            await db.execute(
                "INSERT INTO duel_queue (group_id, next_duel_time, last_p1_id, last_p2_id) VALUES (?,?,?,?)",
                (group_id, next_time, p1_id, p2_id)
            )
        await db.commit()

# ─── WAR SESSION ────────────────────────────────────────────────────────────

async def get_active_war(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM war_sessions WHERE group_id=? AND active=1 ORDER BY id DESC LIMIT 1",
            (group_id,)
        )
        return await cur.fetchone()

async def create_war(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO war_sessions (group_id) VALUES (?)", (group_id,))
        await db.commit()

async def reset_all_clan_points():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE clans SET points=100, wins=0, current_win_streak=0, max_win_streak=0, max_multiplier=0, max_multiplier_user=''")
        await db.commit()
