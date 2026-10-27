from app import slugify


def test_slugify_uses_dashes():
    assert slugify("Hello Big World") == "hello-big-world"


def test_slugify_trims_and_lowercases():
    assert slugify("  Mixed CASE  ") == "mixed-case"
