import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_reddit_webhook_processes_and_redacts_post():
    payload = {
        "title": "Discussion on Hollow Knight Silksong release by gamer_king99",
        "content": "Check out this update! Contact gamer_king99@example.com for info.",
        "score": 800,
        "upvote_ratio": 0.80,
        "num_comments": 120,
        "subreddit": "gaming",
        "url": "https://reddit.com/r/gaming/comments/sample123",
        "author": "gamer_king99",
    }

    response = client.post("/api/v1/webhooks/reddit", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["source"] == "reddit"
    metrics = data["calculated_metrics"]
    assert metrics["score"] == 800
    assert metrics["upvote_ratio"] == 0.80
    assert metrics["estimated_upvotes"] == 1066
    assert metrics["estimated_downvotes"] == 267
    assert metrics["comments"] == 120
    assert metrics["subreddit"] == "gaming"


def test_reddit_webhook_handles_minimal_payload():
    payload = {
        "title": "Minimal title without body or author",
    }

    response = client.post("/api/v1/webhooks/reddit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["calculated_metrics"]["score"] == 0
    assert data["calculated_metrics"]["estimated_upvotes"] == 0


def test_discord_webhook_processes_and_redacts_message():
    payload = {
        "content": "Hey <@123456789> check out Project Luvcraft! Contact user@test.com",
        "author_username": "discord_tester",
        "channel_name": "feedback",
        "guild_name": "Indie Games Studio",
        "message_id": "msg_999888",
        "reactions_count": 42,
    }

    response = client.post("/api/v1/webhooks/discord", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["source"] == "discord"
    metrics = data["calculated_metrics"]
    assert metrics["guild_name"] == "Indie Games Studio"
    assert metrics["channel_name"] == "feedback"
    assert metrics["reactions_count"] == 42
    assert metrics["message_id"] == "msg_999888"

