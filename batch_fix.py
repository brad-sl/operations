# Fixed batch parsing for Coinbase SDK response
def _fetch_all_pairs_batch(self):
    """Batch fetch with chunking (max 20 pairs/request for URL safety)"""
    all_prices = {}
    chunks = [self.pairs[i:i+MAX_BATCH_SIZE] for i in range(0, len(self.pairs), MAX_BATCH_SIZE)]
    
    for chunk_idx, chunk in enumerate(chunks, 1):
        try:
            response = self.cb_client.client.get_products(product_ids=chunk)
            # SDK returns dict with 'products' key containing list of dicts
            if isinstance(response, dict) and 'products' in response:
                for product in response['products']:
                    pair_id = product.get('product_id')
                    price = product.get('price')
                    if pair_id and price:
                        all_prices[pair_id] = float(price)
            self.logger.info(f"✅ Batch {chunk_idx}/{len(chunks)}: {len(chunk)} pairs fetched")
        except Exception as e:
            self.logger.error(f"Batch {chunk_idx} failed: {e} (fallback to individual)")
            for pair in chunk:
                try:
                    single = self.cb_client.client.get_products(product_ids=[pair])
                    if isinstance(single, dict) and 'products' in single and len(single['products']) > 0:
                        prod = single['products'][0]
                        all_prices[pair] = float(prod.get('price', 0))
                except Exception as pe:
                    self.logger.warning(f"Individual fetch {pair}: {pe}")
    return all_prices
