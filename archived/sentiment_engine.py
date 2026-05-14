#!/usr/bin/env python3
"""
Sentiment Engine for Cryptocurrency Trading

A sophisticated, decay-weighted sentiment analysis module
that aggregates multiple data sources with source-specific half-lives.
"""

import math
import time
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

class SentimentEngine:
    """
    A decay-weighted sentiment engine for cryptocurrency trading.
    
    Handles multi-source sentiment aggregation with intelligent decay.
    """
    
    # Default half-lives for different sentiment sources (in seconds)
    DEFAULT_HALF_LIVES = {
        'twitter': 1800,   # 30 minutes
        'reddit': 14400,   # 4 hours
        'news': 1200,      # 20 minutes
        'coingecko': 86400 # 24 hours (slower decay for market indices)
    }
    
    @dataclass
    class SentimentPoint:
        """
        Represents a single sentiment data point
        """
        source: str
        score: float
        timestamp: float
        metadata: Optional[Dict[str, Any]] = None
    
    def __init__(self, 
                 half_lives: Optional[Dict[str, float]] = None, 
                 max_datapoints: int = 1000,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize the Sentiment Engine
        
        Args:
            half_lives (Dict, optional): Custom half-lives for sources
            max_datapoints (int): Maximum number of datapoints to store
            logger (Logger, optional): Custom logger
        """
        # Use provided half-lives or default
        self.half_lives = half_lives or self.DEFAULT_HALF_LIVES
        self.max_datapoints = max_datapoints
        
        # Initialize data storage
        self.data: List[SentimentEngine.SentimentPoint] = []
        
        # Configure logging
        self.logger = logger or logging.getLogger(__name__)
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
    
    def add_sentiment(self, 
                      source: str, 
                      score: float, 
                      timestamp: Optional[float] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a sentiment datapoint to the engine
        
        Args:
            source (str): Source of the sentiment (e.g., 'twitter', 'reddit')
            score (float): Sentiment score (-1 to 1)
            timestamp (float, optional): Unix timestamp
            metadata (Dict, optional): Additional context for the datapoint
        """
        # Use current time if no timestamp provided
        timestamp = timestamp or time.time()
        
        # Validate source and score
        if source not in self.half_lives:
            self.logger.warning(f"Unknown sentiment source '{source}'. Using default half-life.")
            self.half_lives[source] = self.DEFAULT_HALF_LIVES.get('twitter', 1800)
        
        if not -1 <= score <= 1:
            self.logger.warning(f"Sentiment score {score} outside [-1, 1] range. Clipping.")
            score = max(-1, min(1, score))
        
        # Add datapoint
        self.data.append(self.SentimentPoint(source, score, timestamp, metadata))
        
        # Prune excess datapoints
        if len(self.data) > self.max_datapoints:
            self.data = self.data[-self.max_datapoints:]
    
    def _decay_weight(self, source: str, age_seconds: float) -> float:
        """
        Compute exponential decay weight for a datapoint
        
        Args:
            source (str): Sentiment source
            age_seconds (float): Age of the datapoint in seconds
        
        Returns:
            float: Decay weight (0 to 1)
        """
        half_life = self.half_lives.get(source, self.DEFAULT_HALF_LIVES['twitter'])
        lambda_value = math.log(2) / half_life
        return math.exp(-lambda_value * age_seconds)
    
    def compute_index(self, now: Optional[float] = None) -> Dict[str, Any]:
        """
        Compute the unified sentiment index with detailed analytics
        
        Args:
            now (float, optional): Current timestamp for calculation
        
        Returns:
            Dict containing sentiment index and detailed breakdown
        """
        # Use current time if not provided
        now = now or time.time()
        
        # Compute weighted sentiment
        weighted_sum = 0.0
        weight_total = 0.0
        source_weights: Dict[str, float] = {}
        source_scores: Dict[str, List[float]] = {}
        
        for point in self.data:
            age = now - point.timestamp
            weight = self._decay_weight(point.source, age)
            
            # Track per-source weights and scores
            source_weights[point.source] = source_weights.get(point.source, 0) + weight
            source_scores.setdefault(point.source, []).append(point.score)
            
            weighted_sum += weight * point.score
            weight_total += weight
        
        # Prevent division by zero
        sentiment_index = weighted_sum / weight_total if weight_total > 0 else 0.0
        
        # Detailed analytics
        return {
            'sentiment_index': sentiment_index,
            'total_weight': weight_total,
            'source_breakdown': {
                source: {
                    'weight': source_weights.get(source, 0),
                    'avg_score': sum(scores) / len(scores) if scores else 0,
                    'num_points': len(scores)
                } for source, scores in source_scores.items()
            },
            'timestamp': now
        }
    
    def prune(self, max_age_seconds: int) -> None:
        """
        Remove datapoints older than max_age_seconds
        
        Args:
            max_age_seconds (int): Maximum age of datapoints to keep
        """
        now = time.time()
        self.data = [
            point for point in self.data
            if (now - point.timestamp) <= max_age_seconds
        ]
    
    def reset(self) -> None:
        """
        Clear all sentiment data
        """
        self.data.clear()

def main():
    """
    Example usage and testing of the Sentiment Engine
    """
    # Initialize engine with custom half-lives
    engine = SentimentEngine({
        'twitter': 1800,   # 30 minutes
        'reddit': 14400,   # 4 hours
        'news': 1200,      # 20 minutes
        'coingecko': 86400 # 24 hours
    })
    
    # Simulate adding sentiment datapoints
    current_time = time.time()
    
    # Recent Twitter sentiment
    engine.add_sentiment('twitter', 0.7, current_time - 600)  # 10 minutes ago
    
    # Slightly older Reddit sentiment
    engine.add_sentiment('reddit', -0.3, current_time - 3600)  # 1 hour ago
    
    # News sentiment
    engine.add_sentiment('news', 0.5, current_time - 1200)  # 20 minutes ago
    
    # Compute and print sentiment index
    result = engine.compute_index()
    print("Sentiment Analysis Results:")
    print(f"Sentiment Index: {result['sentiment_index']:.4f}")
    print("\nSource Breakdown:")
    for source, details in result['source_breakdown'].items():
        print(f"{source.capitalize()}:")
        print(f"  Weight: {details['weight']:.4f}")
        print(f"  Avg Score: {details['avg_score']:.4f}")
        print(f"  Number of Points: {details['num_points']}")

if __name__ == '__main__':
    main()