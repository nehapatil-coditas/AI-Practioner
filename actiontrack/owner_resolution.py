"""Module 03 — Owner Resolution.

Resolves a raw owner name (from Module 01) to a confirmed identity, an
ambiguous marker, or null — using the note's attendee list plus a running
"known people" picture accumulated across ingested notes. See
modules/03-owner-resolution/SPEC.md.

`OwnerDirectory` holds that accumulated picture. One instance is expected to
live for the lifetime of an `ingest` run (and, longer-term, be persisted
across runs via Module 04 through `to_dict`/`from_dict`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OwnerResolution:
    """Result of resolving one raw owner reference."""

    identity: str | None
    status: str  # "confirmed" | "ambiguous" | "unassigned"


def _normalize(name: str) -> str:
    return " ".join(name.strip().split())


def _first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else ""


def _has_disambiguating_detail(raw: str) -> bool:
    return len(raw.split()) >= 2 or "@" in raw


def _looks_like_initial(token: str) -> bool:
    token = token.rstrip(".")
    return len(token) == 1 and token.isalpha()


def _ambiguous_marker(first_name: str) -> str:
    return f"{first_name.capitalize()} (ambiguous)"


class OwnerDirectory:
    """Accumulated picture of known people, built up across notes.

    Identities are tracked case/whitespace-insensitively so the same person
    referred to with different capitalization always resolves to one
    canonical display string (whichever casing was seen first).
    """

    def __init__(self) -> None:
        # normalized lowercase key -> canonical display name (first-seen casing)
        self._canonical: dict[str, str] = {}
        # first name (lowercase) -> set of canonical keys known under it
        self._by_first_name: dict[str, set[str]] = {}

    def register(self, full_name: str) -> str:
        """Record a known full identity. Returns the canonical display form
        (reusing the casing first seen for this name)."""
        full_name = _normalize(full_name)
        if not full_name:
            return full_name

        key = full_name.lower()
        if key not in self._canonical:
            self._canonical[key] = full_name

        display = self._canonical[key]
        first_key = _first_name(display).lower()
        self._by_first_name.setdefault(first_key, set()).add(key)
        return display

    def register_many(self, full_names: list[str]) -> None:
        for name in full_names:
            self.register(name)

    def _match_by_initial(
        self, first_name: str, initial_token: str, attendees: list[str]
    ) -> str | None:
        """Try to merge a 'First I.' reference with a known full name that
        shares the first name and whose last name starts with that initial.
        Returns the matched full name, or None if no unique match exists."""
        initial = initial_token.rstrip(".").lower()

        def last_name_matches(full_name: str) -> bool:
            parts = full_name.split()
            return (
                len(parts) >= 2
                and parts[0].lower() == first_name.lower()
                and parts[-1].lower().startswith(initial)
            )

        attendee_candidates = {
            _normalize(a) for a in attendees if last_name_matches(_normalize(a))
        }
        if len(attendee_candidates) == 1:
            return next(iter(attendee_candidates))
        if len(attendee_candidates) > 1:
            return None

        known_candidates = {
            self._canonical[key]
            for key in self._candidates(first_name)
            if last_name_matches(self._canonical[key])
        }
        if len(known_candidates) == 1:
            return next(iter(known_candidates))
        return None

    def _candidates(self, first_name: str) -> set[str]:
        return self._by_first_name.get(first_name.lower(), set())

    def is_ambiguous(self, first_name: str) -> bool:
        return len(self._candidates(first_name)) > 1

    def _unique_match(self, first_name: str) -> str | None:
        candidates = self._candidates(first_name)
        if len(candidates) == 1:
            return self._canonical[next(iter(candidates))]
        return None

    def resolve(self, raw_owner: str | None, attendees: list[str] | None = None) -> OwnerResolution:
        """Resolve one raw owner reference against this note's attendee
        list and the accumulated directory."""
        if not raw_owner or not raw_owner.strip():
            return OwnerResolution(None, "unassigned")

        raw = _normalize(raw_owner)
        attendees = attendees or []

        # 1. Inline disambiguating detail (last name, initial, email) — the
        #    raw text already identifies a specific person. A bare initial
        #    ("Priya N.") is first matched against known full names sharing
        #    that first name + initial, so it merges with e.g. "Priya Nair"
        #    instead of becoming its own separate identity.
        if _has_disambiguating_detail(raw):
            tokens = raw.split()
            if len(tokens) == 2 and _looks_like_initial(tokens[1]):
                merged = self._match_by_initial(tokens[0], tokens[1], attendees)
                if merged is not None:
                    identity = self.register(merged)
                    return OwnerResolution(identity, "confirmed")
            identity = self.register(raw)
            return OwnerResolution(identity, "confirmed")

        first_name = raw

        # 2. Note's own attendee list — a strong, locally-scoped signal.
        #    Only full names (2+ tokens) in the attendee list count as
        #    disambiguating; bare first names there don't help.
        attendee_matches: dict[str, str] = {}
        for attendee in attendees:
            normalized = _normalize(attendee)
            if len(normalized.split()) < 2:
                continue
            if _first_name(normalized).lower() == first_name.lower():
                attendee_matches.setdefault(normalized.lower(), normalized)

        if len(attendee_matches) == 1:
            identity = self.register(next(iter(attendee_matches.values())))
            return OwnerResolution(identity, "confirmed")
        if len(attendee_matches) > 1:
            self.register_many(list(attendee_matches.values()))
            return OwnerResolution(_ambiguous_marker(first_name), "ambiguous")

        # 3. Accumulated knowledge from previously ingested notes.
        unique = self._unique_match(first_name)
        if unique is not None:
            return OwnerResolution(unique, "confirmed")

        if self.is_ambiguous(first_name):
            return OwnerResolution(_ambiguous_marker(first_name), "ambiguous")

        # 4. Nothing known about this name yet — treat the raw text itself
        #    as a new, distinct (tentative) identity rather than discarding
        #    it. If it later turns out to collide with someone else sharing
        #    the first name, future resolutions will become ambiguous.
        identity = self.register(raw)
        return OwnerResolution(identity, "confirmed")

    def to_dict(self) -> dict:
        """Serializable snapshot, for persistence via Module 04."""
        return {
            "canonical": dict(self._canonical),
            "by_first_name": {k: sorted(v) for k, v in self._by_first_name.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OwnerDirectory":
        directory = cls()
        directory._canonical = dict(data.get("canonical", {}))
        directory._by_first_name = {
            k: set(v) for k, v in data.get("by_first_name", {}).items()
        }
        return directory
