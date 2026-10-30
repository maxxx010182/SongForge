"""Вечера и тексты писем."""

from datetime import datetime

from backend.services.max_funnel import detail_gift_text
from backend.services.max_letters import keep_letter, ready_letter, studio_letter, survey_letter
from backend.services.nudge_schedule import keep_evenings, studio_slots


def _days(slots: list[str]) -> list[str]:
    zone = __import__("zoneinfo").ZoneInfo("Europe/Moscow")
    return [
        datetime.fromisoformat(item).astimezone(zone).date().isoformat()
        for item in slots
    ]


def test_slots_from_monday_afternoon():
    slots = studio_slots("Europe/Moscow", "2026-10-12T09:00:00+00:00")
    assert _days(slots) == [
        "2026-10-12",
        "2026-10-13",
        "2026-10-14",
        "2026-10-18",
    ]


def test_late_evening_does_not_repeat_the_same_night():
    slots = studio_slots("Europe/Moscow", "2026-10-12T17:30:00+00:00")
    assert _days(slots) == ["2026-10-13", "2026-10-14", "2026-10-18"]
    assert _days(keep_evenings("Europe/Moscow", "2026-10-12T17:30:00+00:00")) == [
        "2026-10-14",
        "2026-10-18",
        "2026-10-21",
        "2026-10-25",
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
    assert "для мамы" in keep_letter(mom, 1)


def test_ready_letter_two_kinds_no_rolik():
    mom = ready_letter({"brief_whom": "маме", "segment": "gift"})
    plain = ready_letter({"brief_whom": "", "segment": "just"})
    biz = ready_letter({"brief_whom": "реклама / бренд", "segment": "business"})
    assert mom.startswith("Два варианта для мамы уже звучат")
    assert plain.startswith("Два варианта уже звучат")
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


def test_keep_letters_two_kinds_no_rolik():
    mom = {"brief_whom": "маме", "segment": "gift"}
    plain = {"brief_whom": "", "segment": "just"}
    biz = {"brief_whom": "реклама / бренд", "segment": "business"}
    d3_mom = keep_letter(mom, 0)
    assert d3_mom.startswith("Песня для мамы уже звучит")
    assert "оба для мамы" in d3_mom
    d3_plain = keep_letter(plain, 0)
    assert d3_plain.startswith("Она уже звучит")
    assert keep_letter(biz, 0) == d3_plain
    assert "ролик" not in keep_letter(mom, 0).lower()
    assert "ролик" not in d3_plain.lower()
    assert "ролик" not in keep_letter(biz, 0).lower()
    d7_mom = keep_letter(mom, 1)
    assert "Песню для мамы уже можно поставить" in d7_mom
    d7_plain = keep_letter(plain, 1)
    assert d7_plain.startswith("Два варианта всё ещё ждут")
    assert keep_letter(biz, 1) == d7_plain
    d10_mom = keep_letter(mom, 2)
    assert "Песня для мамы уже ждёт" in d10_mom
    assert "Послушать" in d10_mom
    d10_plain = keep_letter(plain, 2)
    assert "Песня уже ждёт" in d10_plain
    assert "Послушать" in ready_letter(mom)
    assert keep_letter(biz, 2) == d10_plain
    d14_mom = keep_letter(mom, 3)
    assert "последний день" in d14_mom.lower()
    assert "для мамы" in d14_mom
    assert "сохранена" not in d14_mom.lower()
    d14_plain = keep_letter(plain, 3)
    assert "последний день" in d14_plain.lower()
    assert "не купить" in d14_plain
    assert keep_letter(biz, 3) == d14_plain
    lena = keep_letter({"brief_whom": "Лене", "segment": "gift"}, 1)
    assert lena == d7_plain
    assert "Лене" not in lena
