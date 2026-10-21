"""Пять вечеров и тексты писем."""

from datetime import datetime, timezone

from backend.services.max_letters import keep_letter, ready_letter, studio_letter
from backend.services.nudge_schedule import keep_evenings, studio_slots


def test_slots_from_monday_afternoon():
    slots = studio_slots("Europe/Moscow", "2026-10-12T09:00:00+00:00")
    assert len(slots) == 5
    local = [
        datetime.fromisoformat(item).astimezone(timezone.utc).isoformat()
        for item in slots
    ]
    days = [datetime.fromisoformat(item).astimezone(
        __import__("zoneinfo").ZoneInfo("Europe/Moscow")
    ).date().isoformat() for item in local]
    assert days == [
        "2026-10-12",
        "2026-10-14",
        "2026-10-18",
        "2026-10-21",
        "2026-10-25",
    ]


def test_late_evening_does_not_repeat_the_same_night():
    slots = studio_slots("Europe/Moscow", "2026-10-12T17:30:00+00:00")
    zone = __import__("zoneinfo").ZoneInfo("Europe/Moscow")
    days = [
        datetime.fromisoformat(item).astimezone(zone).date().isoformat()
        for item in slots
    ]
    assert days[0] == "2026-10-13"
    assert days[1] == "2026-10-14"
    assert keep_evenings("Europe/Moscow", "2026-10-12T17:30:00+00:00") == slots[1:]


def test_letters_use_the_named_person_and_skip_a_blank_one():
    mom = {"brief_whom": "маме", "segment": "gift", "brief_detail": "рыжая кошка"}
    assert "для мамы" in studio_letter(mom, 0)
    assert "мамы" in studio_letter(mom, 2)
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
    assert "Два варианта Лене уже звучат" in lena


def test_studio_letters_two_kinds_no_rolik():
    mom = {"brief_whom": "маме", "segment": "gift", "brief_detail": "рыжая кошка"}
    plain = {"brief_whom": "", "segment": "just", "brief_detail": ""}
    biz = {"brief_whom": "реклама / бренд", "segment": "business", "brief_detail": ""}
    assert studio_letter(mom, 0).startswith("Черновик для мамы уже есть")
    assert studio_letter(plain, 0).startswith("Черновик уже есть")
    assert studio_letter(biz, 0) == studio_letter(plain, 0)
    assert "ролик" not in studio_letter(mom, 0).lower()
    assert "ролик" not in studio_letter(biz, 0).lower()
    assert studio_letter(mom, 1).startswith("рыжая кошка")
    assert "строчка для мамы" in studio_letter(mom, 1)
    no_scene = {"brief_whom": "маме", "segment": "gift", "brief_detail": ""}
    assert studio_letter(no_scene, 1).startswith("Песня для мамы пока без голоса")
    assert studio_letter(plain, 1).startswith("Черновик пока без голоса")
    assert "Черновик всё ещё в студии" in studio_letter(mom, 2)
    assert "два варианта для мамы" in studio_letter(mom, 2)
    assert studio_letter(plain, 2).startswith("Будет два варианта.")
    assert studio_letter(biz, 2) == studio_letter(plain, 2)
    assert "как маме это включается на кухне" in studio_letter(mom, 3)
    assert studio_letter(plain, 3).startswith("Пара минут — и можно услышать, как черновик звучит")
    assert studio_letter(mom, 4).startswith("Это последнее письмо про черновик для мамы")
    assert studio_letter(plain, 4).startswith("Это последнее письмо про этот черновик")
    assert studio_letter(biz, 4) == studio_letter(plain, 4)


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
    assert "История для мамы уже внутри" in d10_mom
    d10_plain = keep_letter(plain, 2)
    assert "Историю заново рассказывать не нужно" in d10_plain
    assert keep_letter(biz, 2) == d10_plain
    d14_mom = keep_letter(mom, 3)
    assert d14_mom.startswith("Это последнее письмо про песню для мамы")
    d14_plain = keep_letter(plain, 3)
    assert d14_plain.startswith("Это последнее письмо про эту песню")
    assert keep_letter(biz, 3) == d14_plain
    lena = keep_letter({"brief_whom": "Лене", "segment": "gift"}, 1)
    assert "Песню Лене уже можно поставить" in lena
