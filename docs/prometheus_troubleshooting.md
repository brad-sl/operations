# Prometheus Metrics Endpoint Troubleshooting

## Diagnosis: `dial tcp: lookup bot on 127.0.0.11:53: server misbehaving`

### Potential Causes
1. **Docker Network Resolution**
   - Default Docker DNS might be misconfigured
   - Service name resolution failing

### Debugging Steps
1. Verify Metrics Endpoint in Bot Code
```python
def _setup_prometheus_metrics(self):
    try:
        # Explicit host binding
        start_http_server(
            port=8502, 
            addr='0.0.0.0',  # Listen on all interfaces
            registry=REGISTRY
        )
        self.logger.info(f"Metrics server started on ALL interfaces :8502")
    except Exception as e:
        self.logger.error(f"Metrics server startup failed: {e}")
```

2. Docker Compose Network Configuration
```yaml
networks:
  trading_network:
    driver: bridge
    name: trading_network  # Explicit network name

services:
  bot:
    networks:
      - trading_network
    ports:
      - "8502:8502"  # Expose metrics port

  prometheus:
    networks:
      - trading_network
    extra_hosts:
      - "bot:host-gateway"  # Explicit host resolution
```

3. Prometheus Configuration Debug
```yaml
scrape_configs:
  - job_name: 'trading_bot'
    static_configs:
      - targets: 
        - 'localhost:8502'  # Fallback to localhost
        - 'host.docker.internal:8502'  # Cross-platform resolution
```

## Verification Commands
```bash
# Check Docker networks
docker network ls
docker network inspect trading_network

# Verify service resolution
docker exec -it prometheus_container nslookup bot

# Test metrics endpoint
curl http://localhost:8502/metrics
```

## Recommended Configuration
1. Use explicit network
2. Bind metrics to `0.0.0.0`
3. Add cross-platform host resolution
4. Implement robust logging