"""Run a command with Doppler secrets loaded through the REST API.

This avoids the Doppler CLI keyring path, which is unreliable on this machine.
It reads DOPPLER_TOKEN from the environment and never prints secret values.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


API_URL = "https://api.doppler.com/v3/configs/config/secrets"


def _auth_header(token: str) -> str:
    raw = f"{token}:".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _secret_value(value):
    if isinstance(value, dict):
        return value.get("computed") or value.get("raw") or value.get("value")
    if isinstance(value, str):
        return value
    return None


def fetch_secrets(project: str, config: str) -> dict[str, str]:
    token = os.environ.get("DOPPLER_TOKEN")
    if not token:
        raise RuntimeError("DOPPLER_TOKEN is not set in this process environment.")

    url = f"{API_URL}?project={project}&config={config}"
    req = urllib.request.Request(url, headers={"Authorization": _auth_header(token)})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Doppler read failed: HTTP {exc.code}") from None

    result = {}
    for key, value in payload.get("secrets", {}).items():
        secret = _secret_value(value)
        if secret is not None:
            result[key] = secret
    return result


def set_secret(key: str, value: str, project: str = "agentop", config: str = "prd") -> None:
    token = os.environ.get("DOPPLER_TOKEN")
    if not token:
        raise RuntimeError("DOPPLER_TOKEN is not set; cannot write rotated secret.")

    body = json.dumps(
        {"project": project, "config": config, "secrets": {key: value}}
    ).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": _auth_header(token),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Doppler write failed: HTTP {exc.code}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a command with Doppler env.")
    parser.add_argument("--project", default="agentop")
    parser.add_argument("--config", default="prd")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing command after --")

    env = os.environ.copy()
    secrets = fetch_secrets(args.project, args.config)
    env.update(secrets)
    print(
        f"Loaded {len(secrets)} Doppler keys from {args.project}/{args.config}; running command.",
        flush=True,
    )
    completed = subprocess.run(command, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
