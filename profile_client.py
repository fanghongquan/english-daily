#!/usr/bin/env python3
"""Failure-safe reader for the private adaptive reading profile."""

import json
import os
import urllib.request
from urllib.parse import urlparse


def default_profile():
    return {
        "profile_version": 1,
        "target_mode": "balanced",
        "ability_score": 50.0,
        "observation_count": 0,
        "target_words": 900,
        "target_new_words": 6,
        "sentence_level": 3,
        "target_comprehension": "85%-90%",
        "trend": "stable",
        "updated_at": None,
    }


def _integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid integer")
    if value < low or value > high:
        raise ValueError("integer out of bounds")
    return value


def _validated_profile(data):
    if not isinstance(data, dict):
        raise ValueError("profile response must be an object")
    profile = data.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    ability = profile.get("ability_score")
    if isinstance(ability, bool) or not isinstance(ability, (int, float)):
        raise ValueError("invalid ability score")
    if not 20 <= float(ability) <= 80:
        raise ValueError("ability score out of bounds")
    comprehension = profile.get("target_comprehension")
    if comprehension != "85%-90%":
        raise ValueError("invalid comprehension target")
    trend = profile.get("trend")
    if trend not in {"harder", "stable", "easier"}:
        raise ValueError("invalid trend")
    result = default_profile()
    result.update({
        "ability_score": float(ability),
        "observation_count": _integer(
            profile.get("observation_count"), 0, 100000),
        "target_words": _integer(profile.get("target_words"), 700, 1100),
        "target_new_words": _integer(
            profile.get("target_new_words"), 5, 8),
        "sentence_level": _integer(profile.get("sentence_level"), 1, 5),
        "target_comprehension": comprehension,
        "trend": trend,
        "updated_at": (
            profile.get("updated_at")
            if isinstance(profile.get("updated_at"), str) else None),
    })
    return result


def fetch_profile(url, token):
    """Return a validated profile, or a fresh balanced default on any error."""
    fallback = default_profile()
    if (not isinstance(url, str)
            or urlparse(url).scheme != "https"
            or not isinstance(token, str)
            or len(token) < 32):
        return fallback
    try:
        body = json.dumps(
            {"op": "profile_get"}, separators=(",", ":")).encode()
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-profile-token": token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
        return _validated_profile(data)
    except Exception:
        return fallback


def load_profile_from_env():
    return fetch_profile(
        os.environ.get("PROFILE_API_URL", ""),
        os.environ.get("PROFILE_READ_TOKEN", ""),
    )
