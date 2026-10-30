"""Вечера и тексты писем."""

from datetime import datetime

from backend.services.max_funnel import detail_gift_text
from backend.services.max_letters import keep_letter, ready_letter, studio_letter, survey_letter
from backend.services.nudge_schedule import hour_ping, keep_plan, studio_slots


def _local(slots: list[str]) -> list[tuple[str, int]]:
    zone = __import__("zoneinfo").ZoneInfo("Europe/Moscow")
    out = []
    for item in slots:
        moment = datetime.fromisoformat(item).astimezone(zone)
        out.append((moment.date().isoformat(), moment.hour))
    return out


def test_hour_ping_day_night_and_early_morning():
    assert _local([hour_ping("Europe/Moscow", datetime.fromisoformat("2026-10-12T12:00:00+00:00"))]) == [
        ("2026-10-12", 16)
    ]
    assert _local([hour_ping("Europe/Moscow", datetime.fromisoformat("2026-10-12T18:30:00+00:00"))]) == [
        ("2026-10-13", 10)
    ]
    assert _local([hour_ping("Europe/Moscow", datetime.fromisoformat("2026-10-12T03:00:00+00:00"))]) == [
        ("2026-10-12", 10)
    ]


def test_slots_from_monday_afternoon():
    slots = studio_slots("Europe/Moscow", "2026-10-12T09:00:00+00:00")
    assert _local(slots) == [
        ("2026-10-12", 13),
        ("2026-10-12", 19),
        ("2026-10-14", 19),
        ("2026-10-18", 19),
    ]


def test_late_evening_does_not_repeat_the_same_night():
    slots = studio_slots("Europe/Moscow", "2026-10-12T17:30:00+00:00")
    assert _local(slots) == [
        ("2026-10-12", 21),
        ("2026-10-13", 19),
        ("2026-10-14", 19),
        ("2026-10-18", 19),
    ]
    plan = keep_plan("Europe/Moscow", "2026-10-12T09:00:00+00:00")
    assert [kind for kind, _ in plan] == [
        "keep_d1",
        "keep_d4",
        "keep_d7",
        "keep_d11",
        "keep_d14",
    ]
    assert _local([due for _, due in plan]) == [
        ("2026-10-12", 19),
        ("2026-10-15", 19),
        ("2026-10-18", 19),
        ("2026-10-22", 19),
        ("2026-10-25", 12),
    ]


def test_letters_use_the_named_person_and_skip_a_blank_one():
    mom = {"brief_whom": "маме", "segment": "gift", "brief_detail": "рыжая кошка"}
    assert "для мамы" in studio_letter(mom, 0)
    assert "песни пока нет" in studio_letter(mom, 0)
    assert "рыжая кошка" in studio_letter(mom, 1)
    plain = {"brief_whom": "", "segment": "just", "brief_detail": ""}
    assert "маме" not in studio_letter(plain, 0)
    business = {"brief_whom": "реклама / бренд", "segment": "business", "brief_detail": ""}
    assert "маме" not in ready_letter(business)
    assert "ролик" not in ready_letter(business).lower()
    assert "для мамы" in keep_letter(mom, "d1")


def test_ready_letter_two_kinds_no_rolik():
    mom = ready_letter({"brief_whom": "маме", "segment": "gift"})
    plain = ready_letter({"brief_whom": "", "segment": "just"})
    biz = ready_letter({"brief_whom": "реклама / бренд", "segment": "business"})
    assert mom.startswith("Песня для мамы готова")
    assert plain.startswith("Песня готова")
    assert biz == plain
    assert "ролик" not in mom.lower()
    assert "ролик" not in biz.lower()
    lena = ready_letter({"brief_whom": "Лене", "segment": "gift"})
    assert lena == plain
    assert "Лене" not in lena


def test_studio_letters_say_the_song_is_not_made_yet():
    mom = {"brief_whom": "маме", "segment": "gift", "brief_detail": "рыжая кошка"}
    plain = {"brief_whom": "", "segment": "just", "brief_detail": ""}
    biz = {"brief_whom": "реклама / бренд", "segment": "business", "brief_detail": ""}
    assert "песни пока нет" in studio_letter(mom, 0)
    assert "для мамы" in studio_letter(mom, 0)
    assert studio_letter(plain, 0).startswith("Анкета уже в студии")
    assert studio_letter(biz, 0) == studio_letter(plain, 0)
    assert "черновик" not in studio_letter(mom, 0).lower()
    assert "ролик" not in studio_letter(mom, 0).lower()
    assert "рыжая кошка" in studio_letter(mom, 1)
    no_scene = {"brief_whom": "маме", "segment": "gift", "brief_detail": ""}
    assert studio_letter(no_scene, 1).startswith("Все пожелания")
    assert "Как это работает" in studio_letter(mom, 2)
    assert "149" in studio_letter(mom, 2)
    assert "Платить заранее не нужно" in studio_letter(mom, 2)
    assert studio_letter(mom, 3).startswith("Последнее напоминание: анкета для мамы")
    assert studio_letter(plain, 3).startswith("Последнее напоминание: анкета ждёт")
    assert studio_letter(biz, 3) == studio_letter(plain, 3)


def test_button_case_and_custom_name_stay_apart():
    assert "из жизни мамы" in detail_gift_text("маме")
    assert "про маме" not in detail_gift_text("маме")
    neutral = detail_gift_text("Лена")
    assert neutral.startswith("Расскажи одну сцену")
    assert "из жизни" not in neutral.split("\n", 1)[0]
    survey = survey_letter({"brief_whom": "маме", "segment": "gift"}, 0)
    assert "для мамы" in survey
    assert "шедевр" not in survey.lower()
    assert "алгоритм" not in survey.lower()


def test_keep_letters_follow_the_fourteen_days():
    mom = {"brief_whom": "маме", "segment": "gift"}
    plain = {"brief_whom": "", "segment": "just"}
    biz = {"brief_whom": "реклама / бренд", "segment": "business"}
    fresh = keep_letter(mom, "d1")
    assert "для мамы" in fresh
    assert "90 секунд" in fresh
    assert keep_letter(plain, "d1").startswith("Два демо-варианта ждут")
    heard = keep_letter(mom, "d1", listened=True)
    assert "149" in heard
    assert "для мамы" not in heard
    assert "МузПлощадк" not in heard
    day4 = keep_letter(mom, "d4")
    assert "149" in day4
    assert "для мамы" in day4
    assert keep_letter(biz, "d4") == keep_letter(plain, "d4")
    day7 = keep_letter(mom, "d7")
    assert "расширенный режим" in day7.lower()
    assert "375" not in day7
    assert "899" not in day7
    day11 = keep_letter(mom, "d11")
    assert "ещё 3 дня" in day11
    assert "МузПлощадк" not in day11
    assert "ролик" not in day11.lower()
    last = keep_letter(mom, "d14")
    assert "последний день" in last.lower()
    assert "для мамы" in last
    assert "149" in last
    assert "сохранена" not in last.lower()
    assert keep_letter(biz, "d14") == keep_letter(plain, "d14")
    lena = keep_letter({"brief_whom": "Лене", "segment": "gift"}, "d1")
    assert "Лене" not in lena
    assert lena == keep_letter(plain, "d1")
