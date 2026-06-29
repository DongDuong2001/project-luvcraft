import re

# Lexicon lists for rule-based English & Vietnamese sentiment analysis
POSITIVE_WORDS = {
    "love", "great", "awesome", "good", "amazing", "beautiful", "perfect", 
    "best", "excellent", "cool", "fan", "like", "thích", "tuyệt", "hay", 
    "đẹp", "tốt", "ngon", "yêu", "thần tượng", "ủng hộ", "chất", "hấp dẫn", 
    "thành công", "phấn khích", "vui", "hài lòng", "mê"
}

NEGATIVE_WORDS = {
    "bad", "hate", "worst", "awful", "terrible", "boring", "disappointing", 
    "crap", "waste", "ghét", "chán", "tệ", "dở", "kém", "yếu", "tồi", 
    "thất vọng", "dở tệ", "phí", "bực", "tức", "nhạt", "kém chất lượng", 
    "lừa đảo", "ghê", "kinh"
}

SPAM_KEYWORDS = [
    "giveaway", "free gift", "subscribe to my channel", "make money online", 
    "whatsapp me", "telegram me", "click here", "free money", "visit my website",
    "nhận quà", "kiếm tiền online", "đăng ký kênh", "liên hệ qua số", "click vào"
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
    if not text:
        return "neutral", 50.0, 1.0
        
    words = [w.strip(".,!?\"'()[]{}") for w in text.lower().split()]
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    
    total = pos_count + neg_count
    if total == 0:
        return "neutral", 50.0, 0.5
        
    # Score between 0.0 and 100.0 (where 50.0 is neutral)
    score = 50.0 + ((pos_count - neg_count) / total) * 50.0
    
    # Clamp score to max 99.99 to fit Numeric(6,4) database column safely
    score = max(0.0, min(99.99, score))
    
    if score > 60.0:
        label = "positive"
    elif score < 40.0:
        label = "negative"
    else:
        label = "neutral"
        
    confidence = 0.5 + (abs(score - 50.0) / 100.0)
    confidence = max(0.0, min(1.0, confidence))
    
    return label, score, confidence


def extract_aspects(text: str) -> list[tuple[str, str, float]]:
    """
    Extract key aspects (music, visuals, gameplay, story) if mentioned in the text
    and calculate their sentiment.
    """
    aspects = []
    text_lower = text.lower()
    keywords = {
        "music": ["music", "song", "soundtrack", "audio", "nhạc", "bài hát", "âm thanh"],
        "visuals": ["graphic", "visual", "art", "animation", "đồ họa", "hình ảnh", "hình"],
        "gameplay": ["gameplay", "play", "mechanics", "chơi", "lối chơi"],
        "story": ["story", "plot", "lore", "narrative", "cốt truyện", "kịch bản", "truyện"]
    }
    for aspect, kw_list in keywords.items():
        if any(kw in text_lower for kw in kw_list):
            label, score, _ = analyze_sentiment(text)
            aspects.append((aspect, label, score))
    return aspects

