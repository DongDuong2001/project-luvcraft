import re

from app.analysis.modules.sentiment import classify_sentiment

SPAM_KEYWORDS = [
    "giveaway",
    "free gift",
    "subscribe to my channel",
    "make money online",
    "whatsapp me",
    "telegram me",
    "click here",
    "free money",
    "visit my website",
    "nhận quà",
    "kiếm tiền online",
    "đăng ký kênh",
    "liên hệ qua số",
    "click vào",
]


def clean_text(text: str) -> str:
    """
    Clean text by removing HTML tags, URLs, and normalizing whitespaces.
    """
    if not text:
        return ""

    # Remove HTML tags
    cleaned = re.sub(r"<.*?>", "", text)

    # Remove URLs
    cleaned = re.sub(r"https?://\S+|www\.\S+", "", cleaned)

    # Normalize whitespaces and newlines
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()


def is_spam(raw_text: str, cleaned_text: str) -> bool:
    """
    Check if a signal is spam or noise based on length and common spam keywords.
    """
    if not cleaned_text or len(cleaned_text) < 10:
        return True

    raw_lower = raw_text.lower()

    # Check for spam keywords
    for keyword in SPAM_KEYWORDS:
        if keyword in raw_lower:
            return True

    # Check for excessive link density or characters if any (heuristics)
    return False


def analyze_sentiment(text: str) -> tuple[str, float, float]:
    """
    Perform rule-based sentiment analysis on the text.
    Returns:
        tuple[str, float, float]: (sentiment_label, sentiment_score, confidence)
        - sentiment_label: "positive" | "neutral" | "negative"
        - sentiment_score: float from 0.0000 to 99.9900 (clamped for Numeric(6, 4))
        - confidence: float from 0.0000 to 1.0000
    """
    classification = classify_sentiment(text)
    if classification is None:
        # Compatibility adapter for tuple-based collector persistence. The new
        # snapshot module skips invalid text instead of storing this fallback.
        return "neutral", 50.0, 0.0
    return (
        classification.label.value,
        classification.score,
        classification.confidence,
    )


def extract_aspects(text: str) -> list[tuple[str, str, float]]:
    """
    Extract key aspects (music, visuals, gameplay, story) if mentioned in the text
    and calculate their sentiment.
    """
    aspects = []
    text_lower = text.lower()
    keywords = {
        "music": [
            "music",
            "song",
            "soundtrack",
            "audio",
            "nhạc",
            "bài hát",
            "âm thanh",
        ],
        "visuals": [
            "graphic",
            "visual",
            "art",
            "animation",
            "đồ họa",
            "hình ảnh",
            "hình",
        ],
        "gameplay": ["gameplay", "play", "mechanics", "chơi", "lối chơi"],
        "story": [
            "story",
            "plot",
            "lore",
            "narrative",
            "cốt truyện",
            "kịch bản",
            "truyện",
        ],
    }
    for aspect, kw_list in keywords.items():
        if any(kw in text_lower for kw in kw_list):
            label, score, _ = analyze_sentiment(text)
            aspects.append((aspect, label, score))
    return aspects
