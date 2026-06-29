from app.services.processing_service import clean_text, is_spam, analyze_sentiment, extract_aspects

def test_clean_text_removes_html():
    raw = "<p>Check out this <b>cool</b> content!</p>"
    expected = "Check out this cool content!"
    assert clean_text(raw) == expected

def test_clean_text_removes_urls():
    raw = "Visit https://google.com or http://example.com/page for details."
    expected = "Visit or for details."
    assert clean_text(raw) == expected

def test_clean_text_normalizes_whitespace():
    raw = "Hello   \n\n  world!\tThis  is a test."
    expected = "Hello world! This is a test."
    assert clean_text(raw) == expected

def test_is_spam_short_text():
    assert is_spam("Short", "Short") is True

def test_is_spam_keywords():
    assert is_spam("This is a FREE GIFT giveaway!", "This is a FREE GIFT giveaway!") is True
    assert is_spam("Contact me via whatsapp me now", "Contact me via whatsapp me now") is True
    assert is_spam("Legitimate video description about gaming.", "Legitimate video description about gaming.") is False

def test_analyze_sentiment_positive():
    text = "This is a great and amazing video! I love it."
    label, score, confidence = analyze_sentiment(text)
    assert label == "positive"
    assert score > 60.0
    assert 0.5 < confidence <= 1.0

def test_analyze_sentiment_negative():
    text = "This is a bad and terrible movie. Hate it."
    label, score, confidence = analyze_sentiment(text)
    assert label == "negative"
    assert score < 40.0
    assert 0.5 < confidence <= 1.0

def test_analyze_sentiment_neutral():
    text = "This is a video of a cat walking on the street."
    label, score, confidence = analyze_sentiment(text)
    assert label == "neutral"
    assert score == 50.0
    assert confidence == 0.5

def test_extract_aspects():
    text = "I love the gameplay and the music of this game! Graphically it is also nice."
    aspects = extract_aspects(text)
    aspect_names = {a[0] for a in aspects}
    assert "gameplay" in aspect_names
    assert "music" in aspect_names
    assert "visuals" in aspect_names
