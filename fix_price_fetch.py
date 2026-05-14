import re

# Read the file
with open('phase5_multi_pair.py', 'r') as f:
    content = f.read()

# Find and replace the _fetch_all_pairs_batch method with a simpler version
old_method = r'def _fetch_all_pairs_batch\(self\):.*?return all_prices'
new_method = '''def _fetch_all_pairs_batch(self):
        """Batch fetch - simplified to use price_wrapper"""
        all_prices = {}
        for pair in self.pairs:
            try:
                price = self.price_wrapper.get_price(pair)
                all_prices[pair] = price
            except Exception as e:
                self.logger.warning(f"Price fetch failed for {pair}: {e}")
        return all_prices'''

# This replacement is too complex with regex, so let's just replace in _process_pair
# Find the problematic lines in _process_pair
old_process = '''# Use ONLY batch-fetched price (already cached on self by run)
            price_attr = pair + "_price"
            price = getattr(self, price_attr, None)
            
            if price is None or price <= 0:
                self.logger.warning(f"Batch price missing for {pair}, skipping cycle")'''

new_process = '''# Get price directly from wrapper
            price = self.price_wrapper.get_price(pair)
            
            if price is None or price <= 0:
                self.logger.warning(f"Price fetch failed for {pair}, skipping cycle")'''

content = content.replace(old_process, new_process)

# Also remove the setattr lines in run() method
old_setattr = '''if pair in batch_prices:
                    setattr(self, f'{pair}_price', batch_prices[pair])'''
new_setattr = '''pass  # prices fetched directly in _process_pair'''

content = content.replace(old_setattr, new_setattr)

# Write back
with open('phase5_multi_pair.py', 'w') as f:
    f.write(content)

print("✅ Fixed price fetch logic")
