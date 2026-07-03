"""Genre and mood resolution — shared helpers without service dependencies."""

_GENRE_FROM_UI: dict[str, str] = {
    "поп": "Pop",
    "рок": "Rock",
    "реп": "Hip-Hop",
    "рэп": "Hip-Hop",
    "рэпчик": "Hip-Hop",
    "хип-хоп": "Hip-Hop",
    "электронная": "Electronic",
    "ло-фай": "Lo-Fi",
    "баллада": "Ballad",
    "р-н-б": "R&B",
    "джаз": "Jazz",
    "классическая": "Classical",
    "шансон": "Chanson",
    "кантри": "Country",
    "регги": "Reggae",
    "металл": "Metal",
    "панк": "Punk",
    "фолк": "Folk",
    "блюз": "Blues",
    "соул": "Soul",
    "фанк": "Funk",
    "трэп": "Trap",
    "дрилл": "Drill",
    "техно": "Techno",
    "хаус": "House",
    "драм-н-бэйс": "Drum and Bass",
    "амбиент": "Ambient",
    "бачата": "Bachata",
    "фламенко": "Flamenco",
}

_GENRE_HINTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("Hip-Hop", "Modern Hip-Hop", ("рэп", "rap", "хип", "hip-hop", "hip hop", "трэп", "trap", "drill", "дрилл", "битмейк", "808")),
    ("Rock", "Alternative Rock", ("рок", "rock", "гитар", "metal", "метал", "панк", "punk")),
    ("Electronic", "Modern Electronic", ("электрон", "electronic", "edm", "техно", "techno", "хаус", "house", "синт", "synth")),
    ("Ballad", "Emotional Ballad", ("баллад", "ballad", "лирич", "нежн", "трогательн")),
    ("Lo-Fi", "Chill Lo-Fi", ("лофи", "lo-fi", "lofi", "чилл", "chill", "расслаб")),
    ("R&B", "Modern R&B", ("r&b", "рнб", "р&б", "соул", "soul")),
    ("Jazz", "Contemporary Jazz", ("джаз", "jazz", "свинг", "swing")),
    ("Classical", "Orchestral", ("классик", "classical", "оркестр", "orchestr", "симфон")),
    ("Country", "Modern Country", ("кантри", "country")),
    ("Metal", "Heavy Metal", ("металл", "metal", "heavy")),
    ("Pop", "Modern Pop", ("поп", "pop", "радио", "хит")),
]

_MOOD_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("melancholic", ("груст", "печал", "тоск", "melanchol", "sad", "одинок")),
    ("romantic", ("любов", "романт", "romantic", "нежн", "свидан")),
    ("dark", ("мрач", "тёмн", "dark", "агресс", "злост", "ярост")),
    ("uplifting", ("радост", "счаст", "энерг", "happy", "upbeat", "весел", "праздн", "мотив")),
    ("adventurous", ("эпич", "эпическ", "epic", "adventur", "героич", "триумф")),
    ("calm", ("спокой", "мирн", "calm", "peace", "медита", "тишин")),
    ("nostalgic", ("ностальг", "воспомин", "прошл", "детств")),
]

SUBGENRE_BY_GENRE: dict[str, str] = {
    "Pop": "Modern Pop",
    "Rock": "Alternative Rock",
    "Hip-Hop": "Modern Hip-Hop",
    "Electronic": "Modern Electronic",
    "Ballad": "Emotional Ballad",
    "Lo-Fi": "Chill Lo-Fi",
    "R&B": "Modern R&B",
    "Jazz": "Contemporary Jazz",
    "Classical": "Orchestral",
    "Country": "Modern Country",
    "Metal": "Heavy Metal",
    "Trap": "Dark Trap",
    "Drill": "UK Drill",
    "Techno": "Peak Time Techno",
    "House": "Deep House",
    "Drum and Bass": "Liquid DnB",
    "Ambient": "Cinematic Ambient",
}


def infer_genre_from_idea(idea: str) -> tuple[str, str]:
    text = idea.lower()
    for genre, subgenre, keywords in _GENRE_HINTS:
        if any(word in text for word in keywords):
            return genre, subgenre
    return "Pop", "Modern Pop"


def infer_mood_from_idea(idea: str) -> str:
    text = idea.lower()
    for mood, keywords in _MOOD_HINTS:
        if any(word in text for word in keywords):
            return mood
    return "uplifting"


def resolve_genre(genre: str, idea: str) -> tuple[str, str]:
    normalized = genre.strip().lower()
    if normalized:
        if normalized in _GENRE_FROM_UI:
            genre_en = _GENRE_FROM_UI[normalized]
            return genre_en, SUBGENRE_BY_GENRE.get(genre_en, "Modern Pop")
        return genre.strip(), SUBGENRE_BY_GENRE.get(genre.strip(), "Modern Pop")
    return infer_genre_from_idea(idea)


def resolve_mood(mood: str, idea: str) -> str:
    if mood.strip():
        return mood.strip().lower()
    return infer_mood_from_idea(idea)