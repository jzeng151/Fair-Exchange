"""Text helpers shared by the data loaders."""
import unicodedata


def normalize(name: str | None) -> str:
    """Case-, accent- and apostrophe-insensitive key, so "Cote d'Ivoire" matches "Côte d’Ivoire"."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    return " ".join(text.lower().split())
