"""
Deterministic feature flag evaluation engine.
Implements:
- CRC32-based deterministic bucketing
- Monotonic percentage rollouts
- Priority-ordered targeting rules
- Safe fallback evaluations
"""

import json
import re
from typing import Any
import zlib

from app.models import FlagSetting, TargetingRule


def compute_bucket(flag_key: str, environment_key: str, salt: str, user_id: str) -> int:
    """
    Computes a deterministic integer in [0, 99] for a given (flag, environment, salt, user_id).
    Pure function: No random numbers, timestamps, or session IDs.
    """
    key = f"{flag_key}:{environment_key}:{salt}:{user_id}".encode("utf-8")
    return zlib.crc32(key) % 100


def match_rule(rule: TargetingRule, attributes: dict[str, Any]) -> bool:
    """
    Evaluates a single targeting rule against user attributes.
    Supports operators: in, not_in, equals, not_equals, contains, regex.
    """
    attr_val = attributes.get(rule.attribute)
    if attr_val is None:
        return False

    try:
        rule_values = json.loads(rule.values)
    except Exception:
        rule_values = [rule.values]

    if not isinstance(rule_values, list):
        rule_values = [rule_values]

    str_attr = str(attr_val).strip()
    norm_values = [str(v).strip() for v in rule_values]

    op = rule.operator.lower().strip()
    if op == "in":
        return str_attr in norm_values
    elif op == "not_in":
        return str_attr not in norm_values
    elif op == "equals":
        return any(str_attr.lower() == v.lower() for v in norm_values)
    elif op == "not_equals":
        return not any(str_attr.lower() == v.lower() for v in norm_values)
    elif op == "contains":
        return any(v.lower() in str_attr.lower() for v in norm_values)
    elif op == "regex":
        for pat in norm_values:
            try:
                if re.search(pat, str_attr):
                    return True
            except re.error:
                continue
        return False

    return False


def evaluate_flag(
    flag_key: str,
    environment_key: str,
    setting: FlagSetting,
    user_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluates a feature flag in an environment for a given user context.
    Evaluation order:
    1. If flag is archived or disabled -> safe default (disabled)
    2. Targeting rules (ordered by priority asc) -> matching rule variant
    3. Rollout percentage bucketing (monotonic) -> on if bucket < percentage else default
    """
    # 1. Disabled or archived check
    if not setting.enabled or (setting.flag and setting.flag.archived_at is not None):
        return {
            "enabled": False,
            "variant": setting.default_variant or "off",
            "reason": "disabled_or_archived",
        }

    user_attrs = dict(attributes or {})
    if user_id:
        user_attrs.setdefault("user_id", user_id)

    # 2. Targeting rules
    if setting.rules:
        sorted_rules = sorted(setting.rules, key=lambda r: r.priority)
        for rule in sorted_rules:
            if match_rule(rule, user_attrs):
                return {
                    "enabled": True,
                    "variant": rule.variant or "on",
                    "reason": f"rule_match:priority_{rule.priority}",
                }

    # 3. Rollout percentage
    percentage = setting.rollout.percentage if setting.rollout else 0
    salt = setting.rollout.salt if setting.rollout else ""

    if percentage <= 0:
        return {
            "enabled": False,
            "variant": setting.default_variant or "off",
            "reason": "rollout_zero",
        }
    if percentage >= 100:
        return {
            "enabled": True,
            "variant": "on",
            "reason": "rollout_100",
        }

    target_id = user_id or str(user_attrs.get("user_id", ""))
    if not target_id:
        return {
            "enabled": False,
            "variant": setting.default_variant or "off",
            "reason": "missing_user_id",
        }

    bucket = compute_bucket(flag_key, environment_key, salt, target_id)
    if bucket < percentage:
        return {
            "enabled": True,
            "variant": "on",
            "reason": f"rollout_bucket_{bucket}_lt_{percentage}",
        }
    else:
        return {
            "enabled": False,
            "variant": setting.default_variant or "off",
            "reason": f"rollout_bucket_{bucket}_gte_{percentage}",
        }
