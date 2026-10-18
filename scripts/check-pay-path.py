#!/usr/bin/env python3
"""Read-only: last songs, payments, and whether the person bought the demo they heard."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path("/root/SongForge/data/songforge.db")
DAYS = 14


def parse_utc(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text[:32])
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def msk(raw: str) -> str:
    stamp = parse_utc(raw)
    if stamp is None:
        return (raw or "")[:16] or "?"
    return (stamp + timedelta(hours=3)).strftime("%d.%m %H:%M")


def one_line(text: str, limit: int = 36) -> str:
    return " ".join((text or "").split())[:limit]


def bought(row: sqlite3.Row) -> bool:
    return int(row["purchased"] or 0) == 1 or int(row["note_charged"] or 0) == 1


def main() -> None:
    if not DB.is_file():
        print(f"базы нет: {DB}")
        return
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    gens = conn.execute(
        """
        SELECT id, user_id, substr(created_at,1,19) AS at, status, title,
               purchased, note_charged
        FROM generations
        WHERE created_at >= ?
        ORDER BY created_at
        """,
        (since,),
    ).fetchall()
    pays = conn.execute(
        """
        SELECT id, user_id, substr(created_at,1,19) AS at,
               substr(COALESCE(paid_at,''),1,19) AS paid,
               status, package_id, notes_amount, price_rub
        FROM payment_orders
        WHERE created_at >= ? OR COALESCE(paid_at,'') >= ?
        ORDER BY created_at
        """,
        (since, since),
    ).fetchall()

    print(f"с {DAYS} дней назад: песен {len(gens)}, заказов {len(pays)}")
    ok = [g for g in gens if (g["status"] or "").lower() == "success"]
    print(
        f"готовых {len(ok)}, из них выкуплено "
        f"{sum(1 for g in ok if bought(g))}, пробных без выкупа "
        f"{sum(1 for g in ok if not bought(g))}"
    )
    paid_n = sum(1 for p in pays if (p["status"] or "").lower() == "paid")
    print(
        f"оплат прошедших {paid_n}, незакрытых "
        f"{sum(1 for p in pays if (p['status'] or '').lower() != 'paid')}"
    )

    by_user: dict[str, list[sqlite3.Row]] = {}
    for row in gens:
        uid = (row["user_id"] or "").strip()
        if uid:
            by_user.setdefault(uid, []).append(row)
    pay_by_user: dict[str, list[sqlite3.Row]] = {}
    for row in pays:
        uid = (row["user_id"] or "").strip()
        if uid:
            pay_by_user.setdefault(uid, []).append(row)

    interesting = set(pay_by_user) | {
        uid for uid, rows in by_user.items() if any(bought(g) for g in rows)
    }
    counts = {
        "выкупил первую": 0,
        "выкупил следующую": 0,
        "оплатил, песню не выкупил": 0,
        "выкупил без свежей оплаты": 0,
    }

    print("--- ПУТЬ ПО ЛЮДЯМ ---")
    shown = 0
    for uid in sorted(
        interesting,
        key=lambda u: (by_user.get(u) or pay_by_user.get(u) or [{"at": ""}])[-1]["at"],
        reverse=True,
    ):
        user = conn.execute(
            "SELECT display_name, balance FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
        name = one_line((user["display_name"] if user else "") or "без имени", 24)
        bal = user["balance"] if user else "?"
        songs = by_user.get(uid, [])
        orders = pay_by_user.get(uid, [])
        success = [g for g in songs if (g["status"] or "").lower() == "success"]
        first = success[0] if success else None
        bought_songs = [g for g in success if bought(g)]
        paid_orders = [p for p in orders if (p["status"] or "").lower() == "paid"]

        if first and bought(first):
            verdict = "выкупил первую"
        elif bought_songs and first and not bought(first):
            verdict = "выкупил следующую"
        elif paid_orders and not bought_songs:
            verdict = "оплатил, песню не выкупил"
        elif bought_songs:
            verdict = "выкупил без свежей оплаты"
        else:
            continue
        counts[verdict] = counts.get(verdict, 0) + 1
        shown += 1
        if shown > 25:
            continue

        print(f"\n{name} | нот сейчас {bal} | {verdict}")
        for g in songs[-6:]:
            lib = conn.execute(
                "SELECT COUNT(*) AS n FROM user_library WHERE generation_id = ?",
                (g["id"],),
            ).fetchone()["n"]
            flag = "выкуп" if bought(g) else (g["status"] or "")
            print(
                f"  песня {msk(g['at'])} | {one_line(g['title'] or '', 32)} | "
                f"{flag} | фонотека {lib}"
            )
        for p in orders[-4:]:
            when = msk(p["paid"] or p["at"])
            print(
                f"  заказ {when} | {p['status']} | {p['package_id']} | "
                f"{p['notes_amount']} нот | {p['price_rub']} ₽"
            )

    if shown > 25:
        print(f"\n… ещё {shown - 25} человек с оплатой или выкупом")
    print("\n--- СВОДКА ---")
    for key, n in counts.items():
        print(f"{key}: {n}")

    print("\n--- ПОСЛЕДНИЕ ГОТОВЫЕ ПЕСНИ ---")
    for g in ok[-12:]:
        uid = (g["user_id"] or "").strip()
        name = "гость"
        if uid:
            user = conn.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (uid,),
            ).fetchone()
            name = one_line((user["display_name"] if user else "") or "без имени", 20)
        flag = "выкуп" if bought(g) else "проба"
        print(
            f"{msk(g['at'])} | {flag} | {name} | {one_line(g['title'] or '', 34)}"
        )


if __name__ == "__main__":
    main()
