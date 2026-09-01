Build a Python class `RateLimiter` that implements a token bucket rate limiter.

Requirements:
- Class name: RateLimiter
- Constructor: __init__(self, rate: float, burst: int) — rate = tokens per second, burst = max tokens
- Method: allow(self) -> bool — returns True if a token is available, consumes one
- Method: tokens_remaining(self) -> float — returns current token count
- Thread-safe (use threading.Lock)
- No external imports (only stdlib)

Example:
```python
rl = RateLimiter(rate=10, burst=5)
assert rl.allow() == True
assert rl.tokens_remaining() == 4.0
```

Write to rate_limiter.py.