"""Доменные знания: маркеры стадий развития технологий и доверие к источникам."""

EMERGENCE_MARKERS = [
    "зарождающ", "ранн", "прототип", "пилот", "лабораторн", "экспериментальн",
    "препринт", "перспектив", "исследован", "научн", "фундаментальн",
    "на стадии", "начальная стадия", "потенциальн", "гипотез", "концепц",
    "доклиническ", "первое упоминание", "на заре", "незрел",
    "emerging", "nascent", "early stage", "early-stage", "prototype", "pilot",
    "preprint", "proof of concept", "proof-of-concept", "frontier",
    "preliminary", "cutting edge", "cutting-edge", "exploratory",
    "fundamental research", "early research", "at an early",
]

MATURITY_MARKERS = [
    "массов", "стандарт", "внедрен", "зрел", "сформировавш", "лидер рынка",
    "лидер", "доминир", "отраслев", "коммерциализ", "промышлен", "индустр",
    "устоявш", "широко", "повсеместн", "производств", "рынок сформир",
    "стадия зрелости", "мейнстрим", "массовое производство", "тираж",
    "mainstream", "mature", "established", "widely adopted", "widely used",
    "industry standard", "incumbent", "commodity", "mass market",
    "mass production", "commercial", "standardized", "commoditized",
    "matured", "legacy",
]

HYPE_MARKERS = [
    "революцион", "прорыв", "сенсаци", "уникальн", "впервые в мире",
    "меняющ", "лучший", "самый", "невероятн", "фантастическ", "бум", "хайп",
    "revolutionary", "breakthrough", "disruptive", "game-chang", "game chang",
    "unprecedented", "world's first", "world first", "hype", "buzz",
    "groundbreaking", "amazing", "the best", "miracle",
]

EARLY_SOURCE_TYPES = {
    "patent", "academic", "scientific", "science", "conference",
    "university", "research", "preprint",
}

SOURCE_TRUST = {
    "patent": 1.00,
    "academic": 1.00,
    "scientific": 1.00,
    "science": 1.00,
    "university": 1.00,
    "research": 1.00,
    "conference": 0.95,
    "preprint": 0.85,
    "government": 0.95,
    "regulator": 0.95,
    "report": 0.90,
    "analytics": 0.90,
    "analyst": 0.90,
    "industry_media": 0.70,
    "media": 0.50,
    "news": 0.50,
    "company": 0.60,
    "press_release": 0.30,
    "social": 0.20,
    "blog": 0.20,
    "aggregator": 0.30,
    "anonymous": 0.10,
    "advert": 0.10,
    "other": 0.40,
}

DEFAULT_SOURCE_TRUST = 0.40

PRIOR_DIRECTIONS = {
    "emergence_ratio": 1,
    "maturity_ratio": -1,
    "hype_ratio": -1,
    "source_trust": 1,
    "early_source": 1,
    "has_patent": 1,
    "has_investment": 1,
    "novelty": 1,
    "low_adoption": 1,
    "growth_rate": 1,
}
