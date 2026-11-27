import threading
import time

import pytest

from mc_helper.features.auth import (
    AuthService,
    LoginLimiter,
    PinVerifier,
    SessionCodec,
)
from mc_helper.shared.clientip import bucket_key, client_ip, parse_networks
from mc_helper.shared.errors import CsrfFailed, Locked, LoginRequired, WrongPin


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_auth(clock: Clock) -> AuthService:
    return AuthService(
        PinVerifier("2468"),
        LoginLimiter(5, 300, clock),
        SessionCodec("k" * 40, "2468", clock),
        7,
    )


def test_lockout_after_five_failures_then_expires() -> None:
    clock = Clock()
    auth = make_auth(clock)
    for _ in range(5):
        with pytest.raises(WrongPin):
            auth.login("1.2.3.4", "0000")
    with pytest.raises(Locked) as locked:
        auth.login("1.2.3.4", "2468")  # even the right PIN is refused while locked
    assert 1 <= locked.value.retry_after_s <= 300
    with pytest.raises(WrongPin):
        auth.login("5.6.7.8", "0000")  # another address is unaffected
    clock.now += 301
    assert auth.login("1.2.3.4", "2468")


def test_success_resets_counter() -> None:
    clock = Clock()
    auth = make_auth(clock)
    for _ in range(4):
        with pytest.raises(WrongPin):
            auth.login("1.2.3.4", "0000")
    auth.login("1.2.3.4", "2468")
    for _ in range(4):
        with pytest.raises(WrongPin):
            auth.login("1.2.3.4", "0000")


def test_pin_hashed_compare() -> None:
    verifier = PinVerifier("2468")
    assert verifier.verify("2468")
    assert not verifier.verify("2469")
    assert not verifier.verify("2468" + "0" * 200)
    assert "2468" not in repr(vars(verifier))


def test_session_tamper_and_expiry() -> None:
    clock = Clock()
    codec = SessionCodec("k" * 40, "2468", clock)
    token, session = codec.issue(authed=True, ttl_seconds=100)
    assert codec.read(token) == session
    body, sig = token.split(".")
    assert codec.read(f"{body}.{sig[:-2]}AA") is None
    other, _ = SessionCodec("z" * 40, "2468", clock).issue(authed=True, ttl_seconds=100)
    assert codec.read(other) is None
    assert codec.read("garbage") is None
    assert codec.read(None) is None
    assert codec.read("a.b") is None
    clock.now += 101
    assert codec.read(token) is None


def test_require_login_and_csrf() -> None:
    auth = make_auth(Clock())
    anon_token, anon = auth.anonymous_session()
    with pytest.raises(LoginRequired):
        auth.require_login(anon_token)
    with pytest.raises(LoginRequired):
        auth.require_login(None)
    with pytest.raises(CsrfFailed):
        auth.check_csrf(anon, None)
    with pytest.raises(CsrfFailed):
        auth.check_csrf(anon, "nope")
    auth.check_csrf(anon, anon.csrf)


def test_client_ip_trusts_forwarded_only_from_proxy() -> None:
    proxies = parse_networks(["10.0.0.0/24"])
    assert client_ip("10.0.0.5", ["192.168.1.9"], proxies) == "192.168.1.9"
    assert client_ip("192.168.1.50", ["1.1.1.1"], proxies) == "192.168.1.50"
    assert client_ip("10.0.0.5", ["junk"], proxies) == "10.0.0.5"
    assert client_ip(None, [], proxies) == "0.0.0.0"
    assert bucket_key("2001:db8:1:2:3:4:5:6") == bucket_key("2001:db8:1:2::9")


def test_session_from_one_pin_is_rejected_under_another() -> None:
    clock = Clock()
    token, _ = SessionCodec("k" * 40, "2468", clock).issue(authed=True, ttl_seconds=100)
    assert SessionCodec("k" * 40, "2468", clock).read(token) is not None
    assert SessionCodec("k" * 40, "1357", clock).read(token) is None


class CountingVerifier(PinVerifier):
    def __init__(self) -> None:
        super().__init__("2468")
        self.calls = 0
        self._guard = threading.Lock()

    def verify(self, attempt: str) -> bool:
        with self._guard:
            self.calls += 1
        time.sleep(0.02)  # a slow hash gives parallel requests time to overlap
        return super().verify(attempt)


def test_parallel_wrong_pins_cannot_exceed_the_limit() -> None:
    clock = Clock()
    verifier = CountingVerifier()
    auth = AuthService(
        verifier, LoginLimiter(5, 300, clock), SessionCodec("k" * 40, "2468", clock), 7
    )
    outcomes: list[type[Exception]] = []
    guard = threading.Lock()
    barrier = threading.Barrier(20)

    def attempt() -> None:
        barrier.wait()
        try:
            auth.login("1.2.3.4", "0000")
        except (WrongPin, Locked) as exc:
            with guard:
                outcomes.append(type(exc))

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert verifier.calls <= 5
    assert outcomes.count(WrongPin) <= 5
    assert outcomes.count(Locked) >= 15


def test_multi_hop_forwarded_chain_and_malformed_entries() -> None:
    proxies = parse_networks(["10.0.0.0/24", "10.0.1.0/24"])
    # right-most untrusted entry wins; a client cannot prepend its own claim
    assert client_ip("10.0.0.5", ["6.6.6.6, 192.168.1.9, 10.0.1.7"], proxies) == "192.168.1.9"
    assert client_ip("10.0.0.5", ["6.6.6.6", "192.168.1.9, 10.0.1.7"], proxies) == "192.168.1.9"
    # a malformed entry reached before an untrusted one falls back to the peer
    assert client_ip("10.0.0.5", ["192.168.1.9, junk"], proxies) == "10.0.0.5"
    assert client_ip("10.0.0.5", ["10.0.1.7"], proxies) == "10.0.0.5"  # no untrusted entry
    assert client_ip("10.0.0.5", [], proxies) == "10.0.0.5"
    assert client_ip("::ffff:10.0.0.5", ["192.168.1.9"], proxies) == "192.168.1.9"
