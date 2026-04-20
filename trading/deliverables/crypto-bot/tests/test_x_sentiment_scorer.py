"""
Unit tests for X Sentiment Scorer module
Tests sentiment scoring logic, batch processing, and API error handling
"""

import pytest
from datetime import datetime
from src.sentiment.x_api import XSentimentScorer, SentimentResult


class TestXSentimentScorer:
    """Test XSentimentScorer initialization and basic functionality"""

    def test_init_valid_token(self):
        """Test initialization with valid bearer token"""
        scorer = XSentimentScorer("valid_bearer_token_123456")
        assert scorer.bearer_token == "valid_bearer_token_123456"
        assert scorer.base_url == "https://api.twitter.com/2"

    def test_init_invalid_token_empty(self):
        """Test initialization with empty token raises ValueError"""
        with pytest.raises(ValueError, match="Invalid X Bearer Token"):
            XSentimentScorer("")

    def test_init_invalid_token_too_short(self):
        """Test initialization with token too short raises ValueError"""
        with pytest.raises(ValueError, match="Invalid X Bearer Token"):
            XSentimentScorer("short")

    def test_headers_setup(self):
        """Test that headers are properly configured with bearer token"""
        scorer = XSentimentScorer("test_token_123456")
        assert "Authorization" in scorer.session.headers
        assert scorer.session.headers["Authorization"] == "Bearer test_token_123456"


class TestSentimentScoring:
    """Test sentiment scoring logic"""

    @pytest.fixture
    def scorer(self):
        """Fixture: Initialize scorer with valid token"""
        return XSentimentScorer("test_bearer_token_123456")

    def test_score_sentiment_very_bearish(self, scorer):
        """Test very bearish sentiment (crash + dump + liquidation)"""
        text = "Bitcoin crash incoming! Market dump and liquidation fears 🔴"
        score, reasoning = scorer.score_sentiment(text)
        assert score < -0.7, f"Expected very bearish (< -0.7), got {score}"
        assert "crash" in reasoning.lower()

    def test_score_sentiment_very_bullish(self, scorer):
        """Test very bullish sentiment (pump + rally + breakout)"""
        text = "Bitcoin pump! Rally breakout above $50k with FOMO momentum 🚀"
        score, reasoning = scorer.score_sentiment(text)
        assert score > 0.7, f"Expected very bullish (> 0.7), got {score}"
        assert "pump" in reasoning.lower() or "rally" in reasoning.lower()

    def test_score_sentiment_bearish(self, scorer):
        """Test bearish sentiment"""
        text = "Weak market decline concerns"
        score, reasoning = scorer.score_sentiment(text)
        assert score < 0.0, f"Expected bearish (< 0), got {score}"

    def test_score_sentiment_bullish(self, scorer):
        """Test bullish sentiment"""
        text = "Strong market recovery"
        score, reasoning = scorer.score_sentiment(text)
        assert 0.0 < score, f"Expected bullish (> 0), got {score}"

    def test_score_sentiment_neutral(self, scorer):
        """Test neutral sentiment"""
        text = "Bitcoin trading sideways at current price levels"
        score, reasoning = scorer.score_sentiment(text)
        assert -0.3 <= score <= 0.3, f"Expected neutral (~0), got {score}"

    def test_score_sentiment_empty_text(self, scorer):
        """Test empty text returns neutral score"""
        score, reasoning = scorer.score_sentiment("")
        assert score == 0.0
        assert "empty" in reasoning.lower()

    def test_score_sentiment_clamping(self, scorer):
        """Test that scores are clamped to [-1.0, 1.0] range"""
        # Create text with many bearish keywords to exceed -1.0
        text = "crash dump rug liquidation liquidating collapse capitulation weakness"
        score, reasoning = scorer.score_sentiment(text)
        assert -1.0 <= score <= 1.0, f"Score should be clamped, got {score}"
        assert score == -1.0, "Extremely bearish text should clamp to -1.0"

    def test_score_sentiment_case_insensitive(self, scorer):
        """Test sentiment scoring is case-insensitive"""
        text1 = "Bitcoin PUMP rally BREAKOUT"
        text2 = "bitcoin pump rally breakout"
        score1, _ = scorer.score_sentiment(text1)
        score2, _ = scorer.score_sentiment(text2)
        assert score1 == score2, "Scoring should be case-insensitive"

    def test_reasoning_contains_keywords(self, scorer):
        """Test reasoning explains which keywords were detected"""
        text = "Bitcoin pump with strong bullish sentiment"
        _, reasoning = scorer.score_sentiment(text)
        assert "Keywords" in reasoning or "empty" in reasoning.lower() or "strong" in reasoning.lower()


class TestBatchProcessing:
    """Test batch scoring functionality"""

    @pytest.fixture
    def scorer(self):
        """Fixture: Initialize scorer"""
        return XSentimentScorer("test_bearer_token_123456")

    @pytest.fixture
    def sample_tweets(self):
        """Fixture: Sample tweets for batch processing"""
        return [
            {
                "id": "1",
                "text": "Bitcoin pump! Breakout above $50k 🚀",
                "author": "@bull_trader",
                "created_at": "2026-03-23T10:00:00Z",
            },
            {
                "id": "2",
                "text": "Market crash and liquidation fears",
                "author": "@bear_analyst",
                "created_at": "2026-03-23T10:05:00Z",
            },
            {
                "id": "3",
                "text": "Bitcoin trading sideways, waiting for breakout",
                "author": "@technical_trader",
                "created_at": "2026-03-23T10:10:00Z",
            },
        ]

    def test_score_batch_returns_list(self, scorer, sample_tweets):
        """Test score_batch returns list of results"""
        results = scorer.score_batch(sample_tweets)
        assert isinstance(results, list)
        assert len(results) == 3

    def test_score_batch_result_structure(self, scorer, sample_tweets):
        """Test each result has required fields"""
        results = scorer.score_batch(sample_tweets)
        required_fields = {"timestamp", "tweet_id", "author", "text", "sentiment_score", "reasoning"}
        for result in results:
            assert all(field in result for field in required_fields)
            assert isinstance(result["sentiment_score"], float)
            assert -1.0 <= result["sentiment_score"] <= 1.0

    def test_score_batch_empty_list(self, scorer):
        """Test score_batch with empty list returns empty list"""
        results = scorer.score_batch([])
        assert results == []

    def test_score_batch_preserves_metadata(self, scorer, sample_tweets):
        """Test batch preserves tweet metadata"""
        results = scorer.score_batch(sample_tweets)
        for original, result in zip(sample_tweets, results):
            assert result["tweet_id"] == original["id"]
            assert result["author"] == original["author"]
            assert result["text"] == original["text"]


class TestAnalysisMethod:
    """Test end-to-end analyze method (local, no API calls)"""

    @pytest.fixture
    def scorer(self):
        """Fixture: Initialize scorer"""
        return XSentimentScorer("test_bearer_token_123456")

    def test_analyze_empty_tweets(self, scorer, monkeypatch):
        """Test analyze handles empty tweet list"""
        # Mock fetch_tweets to return empty list
        monkeypatch.setattr(scorer, "fetch_tweets", lambda *args, **kwargs: [])

        result = scorer.analyze("test query")
        assert result["tweets_fetched"] == 0
        assert result["average_sentiment"] == 0.0
        assert result["results"] == []

    def test_analyze_result_structure(self, scorer, monkeypatch):
        """Test analyze result has required structure"""
        mock_tweets = [
            {
                "id": "1",
                "text": "Bitcoin pump 🚀",
                "author": "@trader",
                "created_at": "2026-03-23T10:00:00Z",
            }
        ]
        monkeypatch.setattr(scorer, "fetch_tweets", lambda *args, **kwargs: mock_tweets)

        result = scorer.analyze("Bitcoin")
        required_fields = {"timestamp", "query", "tweets_fetched", "average_sentiment", "sentiment_distribution", "results"}
        assert all(field in result for field in required_fields)
        assert result["query"] == "Bitcoin"
        assert result["tweets_fetched"] == 1

    def test_sentiment_distribution_calculation(self, scorer, monkeypatch):
        """Test sentiment distribution is calculated correctly"""
        mock_tweets = [
            {"id": "1", "text": "crash dump rug", "author": "@a", "created_at": "2026-03-23T10:00:00Z"},  # very bearish
            {"id": "2", "text": "weakness concern", "author": "@b", "created_at": "2026-03-23T10:05:00Z"},  # bearish
            {"id": "3", "text": "trading sideways", "author": "@c", "created_at": "2026-03-23T10:10:00Z"},  # neutral
            {"id": "4", "text": "strength adoption", "author": "@d", "created_at": "2026-03-23T10:15:00Z"},  # bullish
            {"id": "5", "text": "pump rally breakout", "author": "@e", "created_at": "2026-03-23T10:20:00Z"},  # very bullish
        ]
        monkeypatch.setattr(scorer, "fetch_tweets", lambda *args, **kwargs: mock_tweets)

        result = scorer.analyze("Bitcoin")
        dist = result["sentiment_distribution"]
        assert dist["very_bearish"] >= 1
        assert dist["very_bullish"] >= 1
        assert sum(dist.values()) == len(mock_tweets)


class TestSentimentResultDataclass:
    """Test SentimentResult dataclass"""

    def test_sentiment_result_creation(self):
        """Test creating SentimentResult"""
        result = SentimentResult(
            timestamp="2026-03-23T10:00:00Z",
            tweet_id="123",
            author="@user",
            text="Test tweet",
            sentiment_score=0.5,
            reasoning="Test reasoning",
        )
        assert result.sentiment_score == 0.5

    def test_sentiment_result_to_dict(self):
        """Test converting SentimentResult to dictionary"""
        result = SentimentResult(
            timestamp="2026-03-23T10:00:00Z",
            tweet_id="123",
            author="@user",
            text="Test tweet",
            sentiment_score=0.5,
            reasoning="Test reasoning",
        )
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["tweet_id"] == "123"
        assert result_dict["sentiment_score"] == 0.5


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.fixture
    def scorer(self):
        return XSentimentScorer("test_token_123456")

    def test_very_long_tweet_text(self, scorer):
        """Test scoring with very long text"""
        long_text = "bullish " * 500  # Very long text
        score, reasoning = scorer.score_sentiment(long_text)
        assert -1.0 <= score <= 1.0

    def test_special_characters_in_text(self, scorer):
        """Test handling special characters"""
        text = "Bitcoin 🚀 pump!!! $$$ 📈 breakout @@@ crash ###"
        score, reasoning = scorer.score_sentiment(text)
        assert isinstance(score, float)

    def test_mixed_bearish_bullish(self, scorer):
        """Test text with mixed bullish and bearish sentiment"""
        text = "Bitcoin pump but crash fears growing"
        score, reasoning = scorer.score_sentiment(text)
        # Should be close to neutral since both sentiments present
        assert isinstance(score, float)

    def test_sentiment_keywords_with_negation(self, scorer):
        """Test keywords in context of negation (limitation)"""
        # Note: Current implementation doesn't handle negation
        # This test documents the limitation
        text = "Bitcoin will NOT crash"
        score, reasoning = scorer.score_sentiment(text)
        # Will detect "crash" keyword despite negation
        # This is a known limitation for future enhancement
        assert isinstance(score, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
