"""Erori explicite ale clientului BSD — fiecare cere o reacție diferită."""


class BSDError(Exception):
    """Eroare generică BSD (după epuizarea retry-urilor)."""

    def __init__(self, message: str, status: int | None = None, path: str = ""):
        super().__init__(message)
        self.status = status
        self.path = path


class BSDAuthError(BSDError):
    """401: token lipsă/invalid. Nu are rost să reîncercăm."""


class BSDBadRequest(BSDError):
    """400: parametru invalid (API-ul v2 respinge parametrii necunoscuți)."""


class EndpointNotEntitled(BSDError):
    """402/403 (ex. ``bookmakers_not_entitled``): endpoint plătit pe cheie Free."""


class PaidEndpointBlocked(BSDError):
    """Blocat local, ÎNAINTE de cerere: endpoint care pe planul Free dă mereu 403."""


class QuotaExhausted(BSDError):
    """429 ``taster_exhausted``: cota zilnică s-a terminat (reset la 00:00 UTC)."""


class BudgetExceeded(BSDError):
    """Bugetul local (zilnic sau per rulare) nu permite cererea."""
