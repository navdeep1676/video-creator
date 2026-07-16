from __future__ import annotations

from typing import Any

# Languages offered in the product UI (ISO 639-1 + labels)
LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "label": "English"},
    {"code": "hi", "label": "Hindi"},
    {"code": "es", "label": "Spanish"},
    {"code": "fr", "label": "French"},
    {"code": "de", "label": "German"},
    {"code": "pt", "label": "Portuguese"},
    {"code": "it", "label": "Italian"},
    {"code": "ar", "label": "Arabic"},
    {"code": "zh", "label": "Chinese (Mandarin)"},
    {"code": "ja", "label": "Japanese"},
    {"code": "ko", "label": "Korean"},
    {"code": "tr", "label": "Turkish"},
    {"code": "id", "label": "Indonesian"},
    {"code": "vi", "label": "Vietnamese"},
    {"code": "th", "label": "Thai"},
    {"code": "nl", "label": "Dutch"},
    {"code": "pl", "label": "Polish"},
    {"code": "ru", "label": "Russian"},
    {"code": "bn", "label": "Bengali"},
    {"code": "ta", "label": "Tamil"},
    {"code": "te", "label": "Telugu"},
    {"code": "mr", "label": "Marathi"},
    {"code": "gu", "label": "Gujarati"},
    {"code": "kn", "label": "Kannada"},
    {"code": "ml", "label": "Malayalam"},
    {"code": "pa", "label": "Punjabi"},
]

LANGUAGE_LABELS = {lang["code"]: lang["label"] for lang in LANGUAGES}


def _voice(
    *,
    id: str,
    name: str,
    language: str,
    gender: str,
    edge: str | None = None,
    espeak: str = "en",
    deepgram: str | None = None,
    accent: str = "",
) -> dict[str, Any]:
    providers: list[str] = []
    if deepgram:
        providers.append("deepgram")
    if edge:
        providers.append("edge")
    # Prefer deepgram label when Aura model is primary
    provider = "deepgram" if deepgram else "edge"
    return {
        "id": id,
        "name": name,
        "language": language,
        "language_label": LANGUAGE_LABELS.get(language, language),
        "gender": gender,
        "accent": accent,
        "edge_voice": edge,
        "espeak_voice": espeak,
        "deepgram_model": deepgram,
        "provider": provider,  # primary engine
        "providers": providers,  # all engines that can render this voice
    }


def _aura(
    model: str,
    name: str,
    gender: str,
    language: str = "en",
    accent: str = "",
    edge: str | None = None,
    espeak: str = "en",
) -> dict[str, Any]:
    """Deepgram Aura-2 voice (optional Edge fallback mapping)."""
    return _voice(
        id=model,
        name=name.title() if name.islower() else name,
        language=language,
        gender=gender,
        edge=edge,
        espeak=espeak,
        deepgram=model,
        accent=accent,
    )


# —— Deepgram Aura-2 catalog (primary professional option) ——
# Source: https://developers.deepgram.com/docs/tts-models
_AURA2_EN: list[dict[str, Any]] = [
    _aura("aura-2-thalia-en", "Thalia", "female", accent="American", edge="en-US-AvaNeural", espeak="en-us"),
    _aura("aura-2-andromeda-en", "Andromeda", "female", accent="American", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-helena-en", "Helena", "female", accent="American", edge="en-US-AriaNeural", espeak="en-us"),
    _aura("aura-2-apollo-en", "Apollo", "male", accent="American", edge="en-US-AndrewNeural", espeak="en-us"),
    _aura("aura-2-arcas-en", "Arcas", "male", accent="American", edge="en-US-BrianNeural", espeak="en-us"),
    _aura("aura-2-aries-en", "Aries", "male", accent="American", edge="en-US-GuyNeural", espeak="en-us"),
    _aura("aura-2-asteria-en", "Asteria", "female", accent="American", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-athena-en", "Athena", "female", accent="American", edge="en-US-SaraNeural", espeak="en-us"),
    _aura("aura-2-atlas-en", "Atlas", "male", accent="American", edge="en-US-DavisNeural", espeak="en-us"),
    _aura("aura-2-aurora-en", "Aurora", "female", accent="American", edge="en-US-AvaNeural", espeak="en-us"),
    _aura("aura-2-callista-en", "Callista", "female", accent="American", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-cora-en", "Cora", "female", accent="American", edge="en-US-AriaNeural", espeak="en-us"),
    _aura("aura-2-cordelia-en", "Cordelia", "female", accent="American", edge="en-US-EmmaNeural", espeak="en-us"),
    _aura("aura-2-delia-en", "Delia", "female", accent="American", edge="en-US-AvaNeural", espeak="en-us"),
    _aura("aura-2-draco-en", "Draco", "male", accent="British", edge="en-GB-RyanNeural", espeak="en"),
    _aura("aura-2-electra-en", "Electra", "female", accent="American", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-harmonia-en", "Harmonia", "female", accent="American", edge="en-US-AriaNeural", espeak="en-us"),
    _aura("aura-2-hera-en", "Hera", "female", accent="American", edge="en-US-SaraNeural", espeak="en-us"),
    _aura("aura-2-hermes-en", "Hermes", "male", accent="American", edge="en-US-AndrewNeural", espeak="en-us"),
    _aura("aura-2-hyperion-en", "Hyperion", "male", accent="Australian", edge="en-AU-WilliamNeural", espeak="en"),
    _aura("aura-2-iris-en", "Iris", "female", accent="American", edge="en-US-AvaNeural", espeak="en-us"),
    _aura("aura-2-janus-en", "Janus", "female", accent="American (Southern)", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-juno-en", "Juno", "female", accent="American", edge="en-US-AriaNeural", espeak="en-us"),
    _aura("aura-2-jupiter-en", "Jupiter", "male", accent="American", edge="en-US-BrianNeural", espeak="en-us"),
    _aura("aura-2-luna-en", "Luna", "female", accent="American", edge="en-US-AvaNeural", espeak="en-us"),
    _aura("aura-2-mars-en", "Mars", "male", accent="American", edge="en-US-GuyNeural", espeak="en-us"),
    _aura("aura-2-minerva-en", "Minerva", "female", accent="American", edge="en-US-SaraNeural", espeak="en-us"),
    _aura("aura-2-neptune-en", "Neptune", "male", accent="American", edge="en-US-DavisNeural", espeak="en-us"),
    _aura("aura-2-odysseus-en", "Odysseus", "male", accent="American", edge="en-US-AndrewNeural", espeak="en-us"),
    _aura("aura-2-ophelia-en", "Ophelia", "female", accent="American", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-orion-en", "Orion", "male", accent="American", edge="en-US-BrianNeural", espeak="en-us"),
    _aura("aura-2-orpheus-en", "Orpheus", "male", accent="American", edge="en-US-GuyNeural", espeak="en-us"),
    _aura("aura-2-pandora-en", "Pandora", "female", accent="British", edge="en-GB-SoniaNeural", espeak="en"),
    _aura("aura-2-phoebe-en", "Phoebe", "female", accent="American", edge="en-US-AvaNeural", espeak="en-us"),
    _aura("aura-2-pluto-en", "Pluto", "male", accent="American", edge="en-US-DavisNeural", espeak="en-us"),
    _aura("aura-2-saturn-en", "Saturn", "male", accent="American", edge="en-US-BrianNeural", espeak="en-us"),
    _aura("aura-2-selene-en", "Selene", "female", accent="American", edge="en-US-JennyNeural", espeak="en-us"),
    _aura("aura-2-theia-en", "Theia", "female", accent="Australian", edge="en-AU-NatashaNeural", espeak="en"),
    _aura("aura-2-vesta-en", "Vesta", "female", accent="American", edge="en-US-AriaNeural", espeak="en-us"),
    _aura("aura-2-zeus-en", "Zeus", "male", accent="American", edge="en-US-GuyNeural", espeak="en-us"),
    _aura("aura-2-amalthea-en", "Amalthea", "female", accent="Filipino", edge="en-US-AvaNeural", espeak="en-us"),
]

_AURA2_ES: list[dict[str, Any]] = [
    _aura("aura-2-celeste-es", "Celeste", "female", language="es", accent="Colombian", edge="es-CO-SalomeNeural", espeak="es"),
    _aura("aura-2-estrella-es", "Estrella", "female", language="es", accent="Mexican", edge="es-MX-DaliaNeural", espeak="es"),
    _aura("aura-2-nestor-es", "Nestor", "male", language="es", accent="Peninsular", edge="es-ES-AlvaroNeural", espeak="es"),
    _aura("aura-2-sirio-es", "Sirio", "male", language="es", accent="Mexican", edge="es-MX-JorgeNeural", espeak="es"),
    _aura("aura-2-carina-es", "Carina", "female", language="es", accent="Peninsular", edge="es-ES-ElviraNeural", espeak="es"),
    _aura("aura-2-alvaro-es", "Alvaro", "male", language="es", accent="Peninsular", edge="es-ES-AlvaroNeural", espeak="es"),
    _aura("aura-2-diana-es", "Diana", "female", language="es", accent="Peninsular", edge="es-ES-ElviraNeural", espeak="es"),
    _aura("aura-2-aquila-es", "Aquila", "male", language="es", accent="Latin American", edge="es-MX-JorgeNeural", espeak="es"),
    _aura("aura-2-selena-es", "Selena", "female", language="es", accent="Latin American", edge="es-MX-DaliaNeural", espeak="es"),
    _aura("aura-2-javier-es", "Javier", "male", language="es", accent="Mexican", edge="es-MX-JorgeNeural", espeak="es"),
    _aura("aura-2-agustina-es", "Agustina", "female", language="es", accent="Peninsular", edge="es-ES-ElviraNeural", espeak="es"),
    _aura("aura-2-antonia-es", "Antonia", "female", language="es", accent="Argentine", edge="es-AR-ElenaNeural", espeak="es"),
    _aura("aura-2-gloria-es", "Gloria", "female", language="es", accent="Colombian", edge="es-CO-SalomeNeural", espeak="es"),
    _aura("aura-2-luciano-es", "Luciano", "male", language="es", accent="Mexican", edge="es-MX-JorgeNeural", espeak="es"),
    _aura("aura-2-olivia-es", "Olivia", "female", language="es", accent="Mexican", edge="es-MX-DaliaNeural", espeak="es"),
    _aura("aura-2-silvia-es", "Silvia", "female", language="es", accent="Peninsular", edge="es-ES-ElviraNeural", espeak="es"),
    _aura("aura-2-valerio-es", "Valerio", "male", language="es", accent="Mexican", edge="es-MX-JorgeNeural", espeak="es"),
]

_AURA2_FR: list[dict[str, Any]] = [
    _aura("aura-2-agathe-fr", "Agathe", "female", language="fr", accent="French", edge="fr-FR-DeniseNeural", espeak="fr"),
    _aura("aura-2-hector-fr", "Hector", "male", language="fr", accent="French", edge="fr-FR-HenriNeural", espeak="fr"),
]

_AURA2_DE: list[dict[str, Any]] = [
    _aura("aura-2-julius-de", "Julius", "male", language="de", accent="German", edge="de-DE-ConradNeural", espeak="de"),
    _aura("aura-2-viktoria-de", "Viktoria", "female", language="de", accent="German", edge="de-DE-KatjaNeural", espeak="de"),
    _aura("aura-2-elara-de", "Elara", "female", language="de", accent="German", edge="de-DE-KatjaNeural", espeak="de"),
    _aura("aura-2-aurelia-de", "Aurelia", "female", language="de", accent="German", edge="de-DE-AmalaNeural", espeak="de"),
    _aura("aura-2-lara-de", "Lara", "female", language="de", accent="German", edge="de-DE-KatjaNeural", espeak="de"),
    _aura("aura-2-fabian-de", "Fabian", "male", language="de", accent="German", edge="de-DE-ConradNeural", espeak="de"),
    _aura("aura-2-kara-de", "Kara", "female", language="de", accent="German", edge="de-DE-AmalaNeural", espeak="de"),
]

_AURA2_NL: list[dict[str, Any]] = [
    _aura("aura-2-rhea-nl", "Rhea", "female", language="nl", accent="Dutch", edge="nl-NL-FennaNeural", espeak="nl"),
    _aura("aura-2-sander-nl", "Sander", "male", language="nl", accent="Dutch", edge="nl-NL-MaartenNeural", espeak="nl"),
    _aura("aura-2-beatrix-nl", "Beatrix", "female", language="nl", accent="Dutch", edge="nl-NL-FennaNeural", espeak="nl"),
    _aura("aura-2-daphne-nl", "Daphne", "female", language="nl", accent="Dutch", edge="nl-NL-FennaNeural", espeak="nl"),
    _aura("aura-2-cornelia-nl", "Cornelia", "female", language="nl", accent="Dutch", edge="nl-NL-FennaNeural", espeak="nl"),
    _aura("aura-2-hestia-nl", "Hestia", "female", language="nl", accent="Dutch", edge="nl-NL-FennaNeural", espeak="nl"),
    _aura("aura-2-lars-nl", "Lars", "male", language="nl", accent="Dutch", edge="nl-NL-MaartenNeural", espeak="nl"),
    _aura("aura-2-roman-nl", "Roman", "male", language="nl", accent="Dutch", edge="nl-NL-MaartenNeural", espeak="nl"),
    _aura("aura-2-leda-nl", "Leda", "female", language="nl", accent="Dutch", edge="nl-NL-FennaNeural", espeak="nl"),
]

_AURA2_IT: list[dict[str, Any]] = [
    _aura("aura-2-livia-it", "Livia", "female", language="it", accent="Italian", edge="it-IT-ElsaNeural", espeak="it"),
    _aura("aura-2-dionisio-it", "Dionisio", "male", language="it", accent="Italian", edge="it-IT-DiegoNeural", espeak="it"),
    _aura("aura-2-melia-it", "Melia", "female", language="it", accent="Italian", edge="it-IT-ElsaNeural", espeak="it"),
    _aura("aura-2-elio-it", "Elio", "male", language="it", accent="Italian", edge="it-IT-DiegoNeural", espeak="it"),
    _aura("aura-2-flavio-it", "Flavio", "male", language="it", accent="Italian", edge="it-IT-DiegoNeural", espeak="it"),
    _aura("aura-2-maia-it", "Maia", "female", language="it", accent="Italian", edge="it-IT-ElsaNeural", espeak="it"),
    _aura("aura-2-cinzia-it", "Cinzia", "female", language="it", accent="Italian", edge="it-IT-ElsaNeural", espeak="it"),
    _aura("aura-2-cesare-it", "Cesare", "male", language="it", accent="Italian", edge="it-IT-DiegoNeural", espeak="it"),
    _aura("aura-2-perseo-it", "Perseo", "male", language="it", accent="Italian", edge="it-IT-DiegoNeural", espeak="it"),
    _aura("aura-2-demetra-it", "Demetra", "female", language="it", accent="Italian", edge="it-IT-ElsaNeural", espeak="it"),
]

_AURA2_JA: list[dict[str, Any]] = [
    _aura("aura-2-fujin-ja", "Fujin", "male", language="ja", accent="Japanese", edge="ja-JP-KeitaNeural", espeak="ja"),
    _aura("aura-2-izanami-ja", "Izanami", "female", language="ja", accent="Japanese", edge="ja-JP-NanamiNeural", espeak="ja"),
    _aura("aura-2-uzume-ja", "Uzume", "female", language="ja", accent="Japanese", edge="ja-JP-NanamiNeural", espeak="ja"),
    _aura("aura-2-ebisu-ja", "Ebisu", "male", language="ja", accent="Japanese", edge="ja-JP-KeitaNeural", espeak="ja"),
    _aura("aura-2-ama-ja", "Ama", "female", language="ja", accent="Japanese", edge="ja-JP-NanamiNeural", espeak="ja"),
]

# —— Free Edge neural voices (multi-language, no API key) ——
_EDGE_FREE: list[dict[str, Any]] = [
    # English free (distinct from Aura ids so both engines show as options)
    _voice(id="edge-en-ava", name="Ava", language="en", gender="female", edge="en-US-AvaNeural", espeak="en-us", accent="American"),
    _voice(id="edge-en-andrew", name="Andrew", language="en", gender="male", edge="en-US-AndrewNeural", espeak="en-us", accent="American"),
    _voice(id="edge-en-sonia", name="Sonia", language="en", gender="female", edge="en-GB-SoniaNeural", espeak="en", accent="British"),
    # Hindi
    _voice(id="hi-swara", name="Swara", language="hi", gender="female", edge="hi-IN-SwaraNeural", espeak="hi"),
    _voice(id="hi-madhur", name="Madhur", language="hi", gender="male", edge="hi-IN-MadhurNeural", espeak="hi"),
    # Spanish free extras
    _voice(id="es-elvira", name="Elvira", language="es", gender="female", edge="es-ES-ElviraNeural", espeak="es", accent="Spain"),
    _voice(id="es-alonso", name="Alonso", language="es", gender="male", edge="es-ES-AlvaroNeural", espeak="es", accent="Spain"),
    _voice(id="es-mx-dalia", name="Dalia", language="es", gender="female", edge="es-MX-DaliaNeural", espeak="es", accent="Mexico"),
    # French free
    _voice(id="fr-denise", name="Denise", language="fr", gender="female", edge="fr-FR-DeniseNeural", espeak="fr"),
    _voice(id="fr-henri", name="Henri", language="fr", gender="male", edge="fr-FR-HenriNeural", espeak="fr"),
    # German free
    _voice(id="de-katja", name="Katja", language="de", gender="female", edge="de-DE-KatjaNeural", espeak="de"),
    _voice(id="de-conrad", name="Conrad", language="de", gender="male", edge="de-DE-ConradNeural", espeak="de"),
    # Portuguese
    _voice(id="pt-francisca", name="Francisca", language="pt", gender="female", edge="pt-BR-FranciscaNeural", espeak="pt", accent="Brazil"),
    _voice(id="pt-antonio", name="Antonio", language="pt", gender="male", edge="pt-BR-AntonioNeural", espeak="pt", accent="Brazil"),
    # Italian free
    _voice(id="it-elsa", name="Elsa", language="it", gender="female", edge="it-IT-ElsaNeural", espeak="it"),
    _voice(id="it-diego", name="Diego", language="it", gender="male", edge="it-IT-DiegoNeural", espeak="it"),
    # Arabic
    _voice(id="ar-salma", name="Salma", language="ar", gender="female", edge="ar-EG-SalmaNeural", espeak="ar"),
    _voice(id="ar-shakir", name="Shakir", language="ar", gender="male", edge="ar-SA-HamedNeural", espeak="ar"),
    # Chinese
    _voice(id="zh-xiaoxiao", name="Xiaoxiao", language="zh", gender="female", edge="zh-CN-XiaoxiaoNeural", espeak="cmn"),
    _voice(id="zh-yunxi", name="Yunxi", language="zh", gender="male", edge="zh-CN-YunxiNeural", espeak="cmn"),
    # Japanese free
    _voice(id="ja-nanami", name="Nanami", language="ja", gender="female", edge="ja-JP-NanamiNeural", espeak="ja"),
    _voice(id="ja-keita", name="Keita", language="ja", gender="male", edge="ja-JP-KeitaNeural", espeak="ja"),
    # Korean
    _voice(id="ko-sunhi", name="Sun-Hi", language="ko", gender="female", edge="ko-KR-SunHiNeural", espeak="ko"),
    _voice(id="ko-injoon", name="InJoon", language="ko", gender="male", edge="ko-KR-InJoonNeural", espeak="ko"),
    # Turkish
    _voice(id="tr-emel", name="Emel", language="tr", gender="female", edge="tr-TR-EmelNeural", espeak="tr"),
    _voice(id="tr-ahmet", name="Ahmet", language="tr", gender="male", edge="tr-TR-AhmetNeural", espeak="tr"),
    # Indonesian
    _voice(id="id-gadis", name="Gadis", language="id", gender="female", edge="id-ID-GadisNeural", espeak="id"),
    _voice(id="id-ardi", name="Ardi", language="id", gender="male", edge="id-ID-ArdiNeural", espeak="id"),
    # Vietnamese
    _voice(id="vi-hoaimy", name="HoaiMy", language="vi", gender="female", edge="vi-VN-HoaiMyNeural", espeak="vi"),
    _voice(id="vi-namminh", name="NamMinh", language="vi", gender="male", edge="vi-VN-NamMinhNeural", espeak="vi"),
    # Thai
    _voice(id="th-premwadee", name="Premwadee", language="th", gender="female", edge="th-TH-PremwadeeNeural", espeak="th"),
    _voice(id="th-niwat", name="Niwat", language="th", gender="male", edge="th-TH-NiwatNeural", espeak="th"),
    # Dutch free
    _voice(id="nl-fenna", name="Fenna", language="nl", gender="female", edge="nl-NL-FennaNeural", espeak="nl"),
    _voice(id="nl-maarten", name="Maarten", language="nl", gender="male", edge="nl-NL-MaartenNeural", espeak="nl"),
    # Polish
    _voice(id="pl-agna", name="Agnieszka", language="pl", gender="female", edge="pl-PL-AgnieszkaNeural", espeak="pl"),
    _voice(id="pl-marek", name="Marek", language="pl", gender="male", edge="pl-PL-MarekNeural", espeak="pl"),
    # Russian
    _voice(id="ru-svetlana", name="Svetlana", language="ru", gender="female", edge="ru-RU-SvetlanaNeural", espeak="ru"),
    _voice(id="ru-dmitry", name="Dmitry", language="ru", gender="male", edge="ru-RU-DmitryNeural", espeak="ru"),
    # Indian languages
    _voice(id="bn-tanishaa", name="Tanishaa", language="bn", gender="female", edge="bn-IN-TanishaaNeural", espeak="bn"),
    _voice(id="bn-bashkar", name="Bashkar", language="bn", gender="male", edge="bn-IN-BashkarNeural", espeak="bn"),
    _voice(id="ta-pallavi", name="Pallavi", language="ta", gender="female", edge="ta-IN-PallaviNeural", espeak="ta"),
    _voice(id="ta-valluvar", name="Valluvar", language="ta", gender="male", edge="ta-IN-ValluvarNeural", espeak="ta"),
    _voice(id="te-shruti", name="Shruti", language="te", gender="female", edge="te-IN-ShrutiNeural", espeak="te"),
    _voice(id="te-mohan", name="Mohan", language="te", gender="male", edge="te-IN-MohanNeural", espeak="te"),
    _voice(id="mr-aarti", name="Aarohi", language="mr", gender="female", edge="mr-IN-AarohiNeural", espeak="mr"),
    _voice(id="mr-manohar", name="Manohar", language="mr", gender="male", edge="mr-IN-ManoharNeural", espeak="mr"),
    _voice(id="gu-dhwani", name="Dhwani", language="gu", gender="female", edge="gu-IN-DhwaniNeural", espeak="gu"),
    _voice(id="gu-niranjan", name="Niranjan", language="gu", gender="male", edge="gu-IN-NiranjanNeural", espeak="gu"),
    _voice(id="kn-sapna", name="Sapna", language="kn", gender="female", edge="kn-IN-SapnaNeural", espeak="kn"),
    _voice(id="kn-gagan", name="Gagan", language="kn", gender="male", edge="kn-IN-GaganNeural", espeak="kn"),
    _voice(id="ml-sobhana", name="Sobhana", language="ml", gender="female", edge="ml-IN-SobhanaNeural", espeak="ml"),
    _voice(id="ml-midhun", name="Midhun", language="ml", gender="male", edge="ml-IN-MidhunNeural", espeak="ml"),
    _voice(id="pa-vaani", name="Vaani", language="pa", gender="female", edge="pa-IN-VaaniNeural", espeak="pa"),
    _voice(id="pa-omesh", name="Omesh", language="pa", gender="male", edge="pa-IN-OmeshNeural", espeak="pa"),
]

VOICES: list[dict[str, Any]] = [
    *_AURA2_EN,
    *_AURA2_ES,
    *_AURA2_FR,
    *_AURA2_DE,
    *_AURA2_NL,
    *_AURA2_IT,
    *_AURA2_JA,
    *_EDGE_FREE,
]

VOICE_BY_ID: dict[str, dict[str, Any]] = {v["id"]: v for v in VOICES}
VOICE_IDS = set(VOICE_BY_ID.keys())


def list_languages() -> list[dict[str, str]]:
    present = {v["language"] for v in VOICES}
    return [lang for lang in LANGUAGES if lang["code"] in present]


def list_voices(
    language: str | None = None,
    provider: str | None = None,
) -> list[dict[str, Any]]:
    """
    provider: deepgram | edge | None (all)
    """
    out = list(VOICES)
    if language:
        code = language.strip().lower()
        out = [v for v in out if v["language"] == code]
    if provider:
        p = provider.strip().lower()
        if p in {"deepgram", "aura", "aura-2", "aura2"}:
            out = [v for v in out if "deepgram" in (v.get("providers") or [])]
        elif p in {"edge", "free"}:
            out = [v for v in out if v.get("provider") == "edge" or (
                "edge" in (v.get("providers") or []) and "deepgram" not in (v.get("providers") or [])
            )]
            # pure edge-only voices for "free" filter
            out = [v for v in out if v.get("provider") == "edge"]
    return out


def get_voice(voice_id: str) -> dict[str, Any] | None:
    return VOICE_BY_ID.get(voice_id)


def default_voice_for_language(language: str, prefer_deepgram: bool = False) -> str:
    voices = list_voices(language)
    if not voices:
        return "aura-2-thalia-en"
    if prefer_deepgram:
        for v in voices:
            if "deepgram" in (v.get("providers") or []) and v.get("gender") == "female":
                return v["id"]
        for v in voices:
            if "deepgram" in (v.get("providers") or []):
                return v["id"]
    for v in voices:
        if v.get("gender") == "female":
            return v["id"]
    return voices[0]["id"]


def public_voice(v: dict[str, Any], *, deepgram_available: bool = False) -> dict[str, Any]:
    providers = list(v.get("providers") or [])
    # Primary runtime engine for this deployment
    if "deepgram" in providers and deepgram_available:
        runtime = "deepgram"
    elif "edge" in providers:
        runtime = "edge"
    elif "deepgram" in providers:
        runtime = "deepgram"  # needs key
    else:
        runtime = "edge"
    return {
        "id": v["id"],
        "name": v["name"],
        "language": v["language"],
        "language_label": v.get("language_label") or LANGUAGE_LABELS.get(v["language"], v["language"]),
        "gender": v["gender"],
        "accent": v.get("accent") or "",
        "provider": v.get("provider") or "edge",
        "providers": providers,
        "runtime_provider": runtime,
        "requires_deepgram_key": "deepgram" in providers and "edge" not in providers,
    }


def tts_provider_status(deepgram_key_present: bool) -> dict[str, Any]:
    return {
        "deepgram_available": bool(deepgram_key_present),
        "edge_available": True,
        "providers": [
            {
                "id": "deepgram",
                "label": "Deepgram Aura 2",
                "available": bool(deepgram_key_present),
                "description": "Premium neural voices (API key required)",
            },
            {
                "id": "edge",
                "label": "Edge (free)",
                "available": True,
                "description": "Free multi-language neural voices, no API key",
            },
        ],
    }
