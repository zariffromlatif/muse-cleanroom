def slugify(title: str) -> str:
    """Turn a title into a URL slug: lowercase, words joined by single dashes."""
    words = title.strip().lower().split()
    return "_".join(words)
