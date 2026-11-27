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
        SessionCodec("k" * 40, clock),
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
    codec = SessionCodec("k" * 40, clock)
    token, session = codec.issue(authed=True, ttl_seconds=100)
    assert codec.read(token) == session
    body, sig = token.split(".")
    assert codec.read(f"{body}.{sig[:-2]}AA") is None
    other, _ = SessionCodec("z" * 40, clock).issue(authed=True, ttl_seconds=100)
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
