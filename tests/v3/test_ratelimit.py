from betpredict.ingest.ratelimit import TokenBucket


def test_token_bucket_spaces_requests_at_rate():
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s

    b = TokenBucket(25, 25, clock=lambda: t[0], sleep=sleep)
    for _ in range(25):
        assert b.acquire() == 0.0  # burst-ul inițial
    waited = sum(b.acquire() for _ in range(25))
    assert abs(waited - 1.0) < 1e-6  # încă 25 de cereri ≈ 1 s la 25 req/s
