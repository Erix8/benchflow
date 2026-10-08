#!/usr/bin/env python3
"""Fail-closed entry point for the not-yet-integrated ASI-Bench verifier.

A missing integration is evaluator infrastructure failure.  It must never be
serialized as reward zero, because zero is reserved for a validly evaluated
submission failure.
"""

from __future__ import annotations


class VerifierNotIntegratedError(RuntimeError):
    """Raised while the repository contains only the integration scaffold."""


def main() -> None:
    raise VerifierNotIntegratedError(
        "ASI-Bench verifier is scaffold-only; scoring has not been integrated"
    )


if __name__ == "__main__":
    main()
