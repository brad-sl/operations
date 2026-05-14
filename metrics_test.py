from prometheus_client import start_http_server, Gauge
import time

# Create a gauge metric
trading_pair_gauge = Gauge('trading_pair_price', 'Current trading pair price', ['pair'])

# Start the metrics server on port 8502
start_http_server(port=8502, addr='0.0.0.0')

# Set a sample value
trading_pair_gauge.labels(pair='BTC-USD').set(73920.5)

# Keep the server running
print("Metrics server started on 0.0.0.0:8502")
while True:
    time.sleep(60)