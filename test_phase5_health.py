#!/usr/bin/env python3
import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test sentiment
try:
    from sentiment_aggregator import SentimentAggregator
    agg = SentimentAggregator()
    reddit = agg.process_sentiment()
    print(f'Reddit sentiment: {reddit}')
except Exception as e:
    print(f'Sentiment fail: {e}')

# Test price
try:
    from price_wrapper import get_price
    price = get_price('BTC-USD')
    print(f'BTC price: {price}')
except Exception as e:
    print(f'Price fail: {e}')

# Test Prometheus port
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('localhost', 8501))
sock.close()
if result == 0:
    print('Prometheus port 8501 open')
else:
    print('Prometheus port 8501 closed')

print('Health check complete')


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_health():
    try:
        # Test arg parse
        if len(sys.argv) < 2:
            logger.error('Missing args')
            return 1
        
        # Test sentiment
        from sentiment_aggregator import SentimentAggregator
        agg = SentimentAggregator()
        reddit = agg.process_sentiment()
        logger.info(f'Reddit: {reddit}')
        
        # Test price
        from price_wrapper import get_price
        price = get_price('BTC-USD')
        logger.info(f'BTC price: {price}')
        
        # Test Prometheus port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 8502))
        sock.close()
        if result == 0:
            logger.info('Prometheus port 8502 open')
        else:
            logger.warning('Prometheus port 8502 closed')
        logger.info('Health green')
        return 0
    except Exception as e:
        logger.error(f'Health fail: {e}')
        return 1

if __name__ == '__main__':
    sys.exit(test_health())
