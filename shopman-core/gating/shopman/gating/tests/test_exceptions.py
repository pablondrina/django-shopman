"""
Tests for Gating exceptions (P2 — BaseError inheritance).
"""

from shopman.utils.exceptions import BaseError
from shopman.gating.exceptions import GatingError, GateError


class TestGatingExceptions:
    """Tests that GatingError inherits from BaseError."""

    def test_gating_error_inherits_base_error(self):
        assert issubclass(GatingError, BaseError)

    def test_gate_error_inherits_gating_error(self):
        assert issubclass(GateError, GatingError)

    def test_gating_error_default_message(self):
        err = GatingError("TOKEN_INVALID")
        assert err.code == "TOKEN_INVALID"
        assert err.message == "Token is invalid or expired"
        assert err.as_dict()["code"] == "TOKEN_INVALID"

    def test_gating_error_custom_message(self):
        err = GatingError("CUSTOM", "My custom error")
        assert err.message == "My custom error"

    def test_gate_error_preserves_gate_name(self):
        err = GateError("G7_BridgeTokenValidity", "Token expired.")
        assert err.gate_name == "G7_BridgeTokenValidity"
        assert err.code == "GATE_FAILED"
        assert err.message == "Token expired."

    def test_gating_error_is_catchable_as_base_error(self):
        """GatingError should be catchable as BaseError."""
        try:
            raise GatingError("TEST")
        except BaseError as e:
            assert e.code == "TEST"
