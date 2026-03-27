#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Policy Validator — automated security checks for sandbox policies.

Runs standalone or integrated into deployment workflows to catch
overly permissive or misconfigured policies before they're applied.

Checks:
  1. Binary-endpoint scope — flag binaries reaching unexpected endpoints
  2. Overly permissive rules — flag method: "*" or access: full
  3. Missing enforcement — flag endpoints without enforcement: enforce
  4. Missing TLS — flag HTTPS endpoints without tls: terminate
  5. Filesystem scope — warn on read_write outside /sandbox and /tmp
"""

from pathlib import Path
from typing import Any

import yaml


class ValidationResult:
    """Collects warnings and errors from policy validation."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if self.passed and not self.warnings:
            lines.append("Policy validation passed — no issues found.")
        return "\n".join(lines)


EXPECTED_BINARY_SCOPE: dict[str, set[str]] = {
    "/usr/local/bin/claude": {
        "api.anthropic.com",
        "integrate.api.nvidia.com",
        "inference-api.nvidia.com",
        "statsig.anthropic.com",
        "sentry.io",
    },
    "/usr/local/bin/openclaw": {
        "integrate.api.nvidia.com",
        "inference-api.nvidia.com",
        "clawhub.com",
        "openclaw.ai",
        "docs.openclaw.ai",
        "registry.npmjs.org",
    },
    "/usr/bin/gh": {"api.github.com", "github.com"},
    "/usr/bin/git": {"api.github.com", "github.com"},
    "/usr/local/bin/npm": {"registry.npmjs.org"},
    "/usr/local/bin/node": {
        "api.telegram.org",
        "discord.com",
        "gateway.discord.gg",
        "cdn.discordapp.com",
    },
}

ALLOWED_WRITE_PATHS = {"/sandbox", "/tmp", "/dev/null", "/sandbox/.openclaw-data"}


def validate_policy(policy_path: str | Path) -> ValidationResult:
    result = ValidationResult()
    policy_path = Path(policy_path)

    if not policy_path.exists():
        result.error(f"Policy file not found: {policy_path}")
        return result

    with policy_path.open() as f:
        policy = yaml.safe_load(f)

    if not policy:
        result.error("Policy file is empty")
        return result

    _check_binary_scope(policy, result)
    _check_permissive_rules(policy, result)
    _check_enforcement(policy, result)
    _check_tls(policy, result)
    _check_filesystem(policy, result)

    return result


def _check_binary_scope(policy: dict[str, Any], result: ValidationResult) -> None:
    network_policies = policy.get("network_policies", {})
    for policy_name, pol in network_policies.items():
        if not isinstance(pol, dict):
            continue
        endpoints = pol.get("endpoints", [])
        binaries = pol.get("binaries", [])
        endpoint_hosts = {ep.get("host", "") for ep in endpoints if isinstance(ep, dict)}
        binary_paths = {b.get("path", "") for b in binaries if isinstance(b, dict)}
        for binary_path in binary_paths:
            expected = EXPECTED_BINARY_SCOPE.get(binary_path)
            if expected is None:
                result.warn(f"[{policy_name}] Unknown binary '{binary_path}' — not in expected scope map")
                continue
            unexpected = endpoint_hosts - expected
            if unexpected:
                result.error(f"[{policy_name}] Binary '{binary_path}' reaches unexpected endpoints: {', '.join(unexpected)}")


def _check_permissive_rules(policy: dict[str, Any], result: ValidationResult) -> None:
    network_policies = policy.get("network_policies", {})
    for policy_name, pol in network_policies.items():
        if not isinstance(pol, dict):
            continue
        for ep in pol.get("endpoints", []):
            if not isinstance(ep, dict):
                continue
            host = ep.get("host", "?")
            if ep.get("access") == "full":
                result.error(f"[{policy_name}] {host}: access: full — use explicit method rules instead")
            for rule in ep.get("rules", []):
                if not isinstance(rule, dict):
                    continue
                allow = rule.get("allow", {})
                if isinstance(allow, dict) and allow.get("method") == "*":
                    result.error(f"[{policy_name}] {host}: method: '*' — restrict to GET+POST")


def _check_enforcement(policy: dict[str, Any], result: ValidationResult) -> None:
    network_policies = policy.get("network_policies", {})
    for policy_name, pol in network_policies.items():
        if not isinstance(pol, dict):
            continue
        for ep in pol.get("endpoints", []):
            if not isinstance(ep, dict):
                continue
            host = ep.get("host", "?")
            if ep.get("enforcement") != "enforce" and ep.get("access") is None:
                result.warn(f"[{policy_name}] {host}: missing enforcement: enforce")


def _check_tls(policy: dict[str, Any], result: ValidationResult) -> None:
    network_policies = policy.get("network_policies", {})
    for policy_name, pol in network_policies.items():
        if not isinstance(pol, dict):
            continue
        for ep in pol.get("endpoints", []):
            if not isinstance(ep, dict):
                continue
            host = ep.get("host", "?")
            port = ep.get("port", 0)
            if port == 443 and ep.get("tls") != "terminate" and ep.get("access") is None:
                result.warn(f"[{policy_name}] {host}:443: missing tls: terminate")


def _check_filesystem(policy: dict[str, Any], result: ValidationResult) -> None:
    fs_policy = policy.get("filesystem_policy", {})
    for path in fs_policy.get("read_write", []):
        if path not in ALLOWED_WRITE_PATHS:
            result.warn(f"Filesystem: read_write includes '{path}' — outside expected scope")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate NemoClaw sandbox policy")
    parser.add_argument("policy_file", nargs="?", default="nemoclaw-blueprint/policies/openclaw-sandbox.yaml")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    result = validate_policy(args.policy_file)
    if args.strict and result.warnings:
        for w in result.warnings:
            result.error(f"(strict) {w}")
        result.warnings.clear()

    print(result.summary())
    exit(0 if result.passed else 1)
