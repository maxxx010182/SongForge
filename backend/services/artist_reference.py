from dataclasses import dataclass


@dataclass(frozen=True)
class ArtistProfile:
    genre: str
    subgenre: str
    style_tags: str
    vocal_description: str
    bpm: int = 0


_PROFILES: list[tuple[tuple[str, ...], ArtistProfile]] = [
    (
        ("баста", "basta", "васта"),
        ArtistProfile(
            genre="Hip-Hop",
            subgenre="Russian Hip-Hop",
            style_tags=(
                "Russian hip-hop, Russian rap, cinematic orchestral hip-hop production, "
                "emotional storytelling rap, deep authoritative male rap vocal, "
                "punchy kick drum, heavy 808 bass, dramatic strings, introspective mood, "
                "modern Russian urban sound"
            ),
            vocal_description="deep authoritative male Russian rap vocal, baritone delivery",
            bpm=92,
        ),
    ),
    (
        ("the weeknd", "weeknd", "уикенд", "викенд"),
        ArtistProfile(
            genre="R&B",
            subgenre="Dark Pop R&B",
            style_tags=(
                "dark atmospheric R&B pop, synth-heavy production, moody reverb, "
                "falsetto male vocal, 80s-inspired synthwave elements, cinematic night drive feel"
            ),
            vocal_description="smooth male R&B vocal with falsetto, emotional delivery",
            bpm=110,
        ),
    ),
    (
        ("billie eilish", "billie", "билли айлиш", "айлиш"),
        ArtistProfile(
            genre="Pop",
            subgenre="Alternative Pop",
            style_tags=(
                "minimal dark alt-pop, whisper vocal style, sub-bass, sparse beats, "
                "intimate bedroom production, eerie atmospheric pads"
            ),
            vocal_description="soft breathy female vocal, whisper-to-power dynamics",
            bpm=85,
        ),
    ),
]


def _normalize_ref(ref: str) -> str:
    text = ref.strip().lower()
    for noise in (
        "звучание как у",
        "звучание как",
        "в стиле",
        "как у",
        "как",
        "sound like",
        "like",
        "стиль",
    ):
        text = text.replace(noise, " ")
    return " ".join(text.split())


def resolve_artist_reference(ref: str) -> ArtistProfile | None:
    if not ref.strip():
        return None
    normalized = _normalize_ref(ref)
    for keys, profile in _PROFILES:
        if any(key in normalized for key in keys):
            return profile
    return None