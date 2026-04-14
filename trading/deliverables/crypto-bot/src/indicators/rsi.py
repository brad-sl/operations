"""
Stochastic RSI Indicator
Calculates RSI and Stochastic RSI from price data
"""

from typing import List, Tuple
import numpy as np


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate Relative Strength Index (RSI)

    Args:
        prices: List of closing prices
        period: RSI lookback period (default 14)

    Returns:
        List of RSI values (0-100), NaN for first `period` values
    """
    if len(prices) < period + 1:
        raise ValueError(f"Need at least {period + 1} price points")

    prices = np.array(prices, dtype=float)
    deltas = np.diff(prices)

    # Separate gains and losses
    seed = deltas[: period + 1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0

    # Calculate RSI
    rsi_values = [np.nan] * period
    rsi_values.append(100 - 100 / (1 + rs) if rs != 0 else 50)

    # Calculate remaining RSI values using smoothing
    for i in range(period + 1, len(prices)):
        delta = deltas[i - 1]
        up = up * (period - 1) / period + (delta if delta > 0 else 0) / period
        down = down * (period - 1) / period + (-delta if delta < 0 else 0) / period
        rs = up / down if down != 0 else 0
        rsi = 100 - 100 / (1 + rs) if rs != 0 else 50
        rsi_values.append(rsi)

    return rsi_values


def calculate_stochastic_rsi(
    prices: List[float], rsi_period: int = 14, k_period: int = 14, d_period: int = 3
) -> Tuple[List[float], List[float]]:
    """
    Calculate Stochastic RSI and Signal Line (%D)

    Stochastic RSI measures where RSI is within its range
    - %K: Current Stochastic RSI
    - %D: Signal line (moving average of %K)

    Args:
        prices: List of closing prices
        rsi_period: RSI lookback period (default 14)
        k_period: Stochastic lookback period (default 14)
        d_period: Signal line period (default 3)

    Returns:
        Tuple of (%K values, %D values), each 0-100
    """
    rsi_values = calculate_rsi(prices, rsi_period)
    rsi_values = np.array(rsi_values)

    # Calculate Stochastic RSI (%K)
    k_values = []
    for i in range(len(rsi_values)):
        if i < rsi_period + k_period - 1:
            k_values.append(np.nan)
        else:
            window = rsi_values[i - k_period + 1 : i + 1]
            rsi_min = np.nanmin(window)
            rsi_max = np.nanmax(window)
            rsi_range = rsi_max - rsi_min

            if rsi_range == 0:
                k = 50.0
            else:
                k = 100 * (rsi_values[i] - rsi_min) / rsi_range
            k_values.append(k)

    k_values = np.array(k_values)

    # Calculate Signal Line (%D) - moving average of %K
    d_values = []
    for i in range(len(k_values)):
        if i < rsi_period + k_period + d_period - 2:
            d_values.append(np.nan)
        else:
            window = k_values[i - d_period + 1 : i + 1]
            d = np.nanmean(window)
            d_values.append(d)

    d_values = np.array(d_values)
    return k_values.tolist(), d_values.tolist()


def get_signal(rsi: float, k: float, d: float) -> str:
    """
    Generate buy/sell signal from RSI and Stochastic RSI

    Args:
        rsi: Current RSI value (0-100)
        k: Current %K value (0-100)
        d: Current %D value (0-100)

    Returns:
        "BUY", "SELL", or "HOLD"
    """
    # Oversold: RSI < 30 and %K < 20
    if rsi < 30 and k < 20:
        return "BUY"

    # Overbought: RSI > 70 and %K > 80
    if rsi > 70 and k > 80:
        return "SELL"

    # Crossover signals
    if k > d and k < 50:  # %K crosses above %D in oversold region
        return "BUY"

    if k < d and k > 50:  # %K crosses below %D in overbought region
        return "SELL"

    return "HOLD"


# Example usage
if __name__ == "__main__":
    # Test with sample data
    prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 111, 110, 112, 114, 115]

    rsi = calculate_rsi(prices, period=14)
    print("RSI:", [f"{v:.2f}" if not np.isnan(v) else "NaN" for v in rsi])

    k, d = calculate_stochastic_rsi(prices, rsi_period=14, k_period=14, d_period=3)
    print("Stochastic RSI %K:", [f"{v:.2f}" if not np.isnan(v) else "NaN" for v in k])
    print("Stochastic RSI %D:", [f"{v:.2f}" if not np.isnan(v) else "NaN" for v in d])

    if not np.isnan(rsi[-1]) and not np.isnan(k[-1]) and not np.isnan(d[-1]):
        signal = get_signal(rsi[-1], k[-1], d[-1])
        print(f"Current signal: {signal}")
