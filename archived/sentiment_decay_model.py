#!/usr/bin/env python3
"""
Sentiment Decay Model for Cryptocurrency Trading

Implements exponential decay for different sentiment sources
with research-backed half-life parameters.
"""

import math
from datetime import datetime, timedelta
from typing import Dict, Any, List

class SentimentDecayModel:
    """
    Advanced sentiment decay model with source-specific half-life parameters
    """
    
    # Predefined half-life parameters for different sources
    HALF_LIFE_CONFIG = {
        'twitter': {
            'base_half_life_minutes': 30,  # Default 30-minute half-life
            'min_half_life': 5,    # Minimum 5 minutes
            'max_half_life': 120,  # Maximum 2 hours
            'lambda_multiplier': 1.0  # Base multiplier
        },
        'reddit': {
            'base_half_life_minutes': 360,  # 6-hour half-life
            'min_half_life': 30,   # Minimum 30 minutes
            'max_half_life': 1440, # Maximum 24 hours
            'lambda_multiplier': 0.7  # Slower decay
        },
        'news': {
            'base_half_life_minutes': 120,  # 2-hour half-life
            'min_half_life': 30,   # Minimum 30 minutes
            'max_half_life': 480,  # Maximum 8 hours
            'lambda_multiplier': 0.85  # Moderate decay
        }
    }
    
    @staticmethod
    def calculate_decay_weight(timestamp: datetime, 
                                source: str = 'twitter', 
                                current_time: datetime = None) -> float:
        """
        Calculate exponential decay weight for a given timestamp
        
        Args:
            timestamp (datetime): Timestamp of the sentiment data point
            source (str): Source of the sentiment (twitter, reddit, news)
            current_time (datetime, optional): Current time for calculation
        
        Returns:
            float: Decay weight between 0 and 1
        """
        # Use current time if not provided
        current_time = current_time or datetime.utcnow()
        
        # Get half-life configuration
        config = SentimentDecayModel.HALF_LIFE_CONFIG.get(source, 
                SentimentDecayModel.HALF_LIFE_CONFIG['twitter'])
        
        # Calculate time difference in minutes
        time_diff_minutes = (current_time - timestamp).total_seconds() / 60
        
        # Calculate decay lambda
        half_life = config['base_half_life_minutes']
        lambda_value = math.log(2) / half_life * config['lambda_multiplier']
        
        # Exponential decay calculation
        decay_weight = math.exp(-lambda_value * time_diff_minutes)
        
        # Ensure weight is between 0 and 1
        return max(0, min(1, decay_weight))
    
    @staticmethod
    def calculate_weighted_sentiment(sentiments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate weighted sentiment across multiple data points
        
        Args:
            sentiments (List[Dict]): List of sentiment data points
        
        Returns:
            Dict with aggregated sentiment metrics
        """
        total_weight = 0
        weighted_sentiment = 0
        
        for entry in sentiments:
            # Extract key information
            sentiment_score = entry.get('sentiment_score', 0.0)
            timestamp = entry.get('timestamp', datetime.utcnow())
            source = entry.get('source', 'twitter')
            
            # Calculate decay weight
            weight = SentimentDecayModel.calculate_decay_weight(timestamp, source)
            
            # Accumulate weighted sentiment
            weighted_sentiment += sentiment_score * weight
            total_weight += weight
        
        # Prevent division by zero
        final_sentiment = (weighted_sentiment / total_weight) if total_weight > 0 else 0.0
        
        return {
            'weighted_sentiment_score': final_sentiment,
            'total_weight': total_weight,
            'sentiment_sources': len(sentiments)
        }

def main():
    """
    Example usage and testing of the Sentiment Decay Model
    """
    # Example sentiment data points
    sample_sentiments = [
        {
            'sentiment_score': 0.7,
            'timestamp': datetime.utcnow() - timedelta(minutes=10),
            'source': 'twitter'
        },
        {
            'sentiment_score': 0.3,
            'timestamp': datetime.utcnow() - timedelta(hours=1),
            'source': 'reddit'
        },
        {
            'sentiment_score': 0.5,
            'timestamp': datetime.utcnow() - timedelta(minutes=30),
            'source': 'news'
        }
    ]
    
    # Calculate weighted sentiment
    result = SentimentDecayModel.calculate_weighted_sentiment(sample_sentiments)
    
    # Print results
    print("Weighted Sentiment Analysis:")
    print(f"Final Sentiment Score: {result['weighted_sentiment_score']:.4f}")
    print(f"Total Weight: {result['total_weight']:.4f}")
    print(f"Sources Analyzed: {result['sentiment_sources']}")

if __name__ == '__main__':
    main()