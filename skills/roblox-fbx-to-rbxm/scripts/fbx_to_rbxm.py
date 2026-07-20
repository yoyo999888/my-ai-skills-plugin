#!/usr/bin/env python3
"""Upload one arbitrary FBX to Roblox and save its cloud-loaded Model as RBXM.

Without --execute this command is a read-only dry-run. Secrets are loaded only
from environment variables or a JSON config file and are never written out.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECIPE_VERSION = "roblox-fbx-to-rbxm-v1"
RBXM_MAGIC = b"<roblox!\x89\xff\r\n\x1a\n"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Config/checkpoint not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON {path}: {exc}") from None
    if not isinstance(value, dict):
        raise SystemExit(f"Expected a JSON object: {path}")
    return value


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(value)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_settings(args: argparse.Namespace, *, strict: bool) -> dict[str, str]:
    config: dict[str, Any] = {}
    config_path_value = args.config or os.environ.get("ROBLOX_UPLOADER_CONFIG", "")
    if config_path_value:
        config_path = Path(config_path_value).expanduser().resolve()
        if config_path.exists():
            config = read_json(config_path)
        elif strict:
            raise SystemExit(f"Config not found: {config_path}")

    owner = nested_dict(config.get("owner")) or nested_dict(config.get("creator"))
    execution = nested_dict(config.get("luauExecution"))
    settings = {
        "apiKey": str(
            os.environ.get("RBXCLOUD_API_KEY")
            or os.environ.get("ROBLOX_API_KEY")
            or config.get("robloxApiKey")
            or ""
        ),
        "creatorId": str(
            args.creator_id
            or os.environ.get("RBXCLOUD_CREATOR_ID")
            or owner.get("id")
            or ""
        ),
        "creatorType": str(
            args.creator_type
            or os.environ.get("RBXCLOUD_CREATOR_TYPE")
            or owner.get("type")
            or "user"
        ).lower(),
        "universeId": str(
            args.universe_id
            or os.environ.get("ROBLOX_LUAU_UNIVERSE_ID")
            or execution.get("universeId")
            or ""
        ),
        "placeId": str(
            args.place_id
            or os.environ.get("ROBLOX_LUAU_PLACE_ID")
            or execution.get("placeId")
            or ""
        ),
        "configPath": config_path_value,
    }
    if settings["creatorType"] not in {"user", "group"}:
        raise SystemExit("Creator type must be user or group")
    if strict:
        missing = [
            label
            for label, key in (
                ("API key", "apiKey"),
                ("creator id", "creatorId"),
                ("Luau Execution universe id", "universeId"),
                ("Luau Execution place id", "placeId"),
            )
            if not settings[key]
        ]
        if missing:
            raise SystemExit("Missing " + ", ".join(missing))
        for key in ("creatorId", "universeId", "placeId"):
            if not settings[key].isdigit():
                raise SystemExit(f"{key} must be numeric")
    return settings


def find_asset_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("assetId", "asset_id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)) and str(candidate).isdigit():
                return str(candidate)
        for child in value.values():
            found = find_asset_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_asset_id(child)
            if found:
                return found
    return ""


def extract_asset_id(text: str) -> str:
    try:
        found = find_asset_id(json.loads(text))
        if found:
            return found
    except (json.JSONDecodeError, TypeError):
        pass
    for pattern in (r"\bassetId\b[^0-9]{0,20}([0-9]+)", r"rbxassetid://([0-9]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def extract_operation_id(text: str) -> str:
    try:
        value = json.loads(text)
        path = value.get("path", "") if isinstance(value, dict) else ""
        if isinstance(path, str) and path.startswith("operations/"):
            return path.split("/", 1)[1]
    except json.JSONDecodeError:
        pass
    match = re.search(r"operations/([0-9a-fA-F-]+)", text)
    return match.group(1) if match else ""


def run_rbxcloud(args: list[str], api_key: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["RBXCLOUD_API_KEY"] = api_key
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def poll_asset_operation(
    binary: str,
    operation_id: str,
    api_key: str,
    poll_ms: int,
    poll_max: int,
) -> str:
    last_output = ""
    for _ in range(poll_max):
        proc = run_rbxcloud(
            [binary, "assets", "get-operation", "--operation-id", operation_id, "--pretty"],
            api_key,
        )
        last_output = proc.stdout
        asset_id = extract_asset_id(proc.stdout)
        if asset_id:
            return asset_id
        try:
            value = json.loads(proc.stdout)
            if isinstance(value, dict) and value.get("done") and value.get("error"):
                raise RuntimeError("Asset operation failed: " + json.dumps(value["error"], ensure_ascii=False))
        except json.JSONDecodeError:
            pass
        time.sleep(poll_ms / 1000)
    raise RuntimeError(f"Asset operation timed out; last response: {last_output[-1000:]}")


def upload_fbx(args: argparse.Namespace, settings: dict[str, str], fbx: Path) -> str:
    binary = args.rbxcloud
    if shutil.which(binary) is None:
        raise RuntimeError(f"rbxcloud executable not found: {binary}")
    command = [
        binary,
        "assets",
        "create",
        "--asset-type",
        "model-fbx",
        "--display-name",
        (args.display_name or fbx.stem)[:50],
        "--description",
        args.description,
        "--creator-id",
        settings["creatorId"],
        "--creator-type",
        settings["creatorType"],
        "--filepath",
        str(fbx),
        "--pretty",
    ]
    proc = run_rbxcloud(command, settings["apiKey"])
    if proc.returncode != 0:
        raise RuntimeError(f"rbxcloud upload failed ({proc.returncode}): {proc.stderr[-2000:]}")
    asset_id = extract_asset_id(proc.stdout)
    if asset_id:
        return asset_id
    operation_id = extract_operation_id(proc.stdout)
    if not operation_id:
        raise RuntimeError(f"rbxcloud returned neither assetId nor operation id: {proc.stdout[-2000:]}")
    return poll_asset_operation(
        binary,
        operation_id,
        settings["apiKey"],
        args.poll_ms,
        args.poll_max,
    )


def request_json(api_key: str, method: str, url: str, body: Any | None = None) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={"x-api-key": api_key, "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-3000:]
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP request failed {url}: {exc}") from None
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return value


def download_binary(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Binary download failed: HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Binary download failed: {exc}") from None


def cloud_script(asset_id: str) -> str:
    if not asset_id.isdigit():
        raise ValueError("asset_id must be numeric")
    return f'''local InsertService = game:GetService("InsertService")
local SerializationService = game:GetService("SerializationService")
local HttpService = game:GetService("HttpService")

local assetId = {asset_id}
local loaded = InsertService:LoadAsset(assetId)
local counts = {{}}
local meshPartCount = 0
for _, instance in ipairs(loaded:GetDescendants()) do
    counts[instance.ClassName] = (counts[instance.ClassName] or 0) + 1
    if instance:IsA("MeshPart") then
        meshPartCount += 1
    end
end
local pivot = {{ loaded:GetPivot():GetComponents() }}
local summary = {{
    status = "loaded",
    modelAssetId = tostring(assetId),
    modelName = loaded.Name,
    modelClassName = loaded.ClassName,
    modelPivotCFrame = pivot,
    descendantCount = #loaded:GetDescendants(),
    meshPartCount = meshPartCount,
    classCounts = counts,
}}
local buffer = SerializationService:SerializeInstancesAsync({{ loaded }})
return {{
    BinaryOutput = buffer,
    ReturnValues = {{ HttpService:JSONEncode(summary) }},
}}
'''


def run_cloud_serialization(
    args: argparse.Namespace,
    settings: dict[str, str],
    asset_id: str,
) -> tuple[bytes, dict[str, Any], str]:
    base = "https://apis.roblox.com/cloud/v2"
    create_url = (
        f"{base}/universes/{settings['universeId']}/places/{settings['placeId']}"
        "/luau-execution-session-tasks"
    )
    created = request_json(
        settings["apiKey"],
        "POST",
        create_url,
        {
            "script": cloud_script(asset_id),
            "enableBinaryOutput": True,
            "timeout": "300s",
        },
    )
    task_path = str(created.get("path") or "")
    if not task_path:
        raise RuntimeError("Luau Execution create response has no task path")

    completed: dict[str, Any] | None = None
    for _ in range(args.task_poll_max):
        state = request_json(settings["apiKey"], "GET", f"{base}/{task_path}")
        if state.get("state") != "PROCESSING":
            completed = state
            break
        time.sleep(args.task_poll_ms / 1000)
    if completed is None:
        raise RuntimeError(f"Luau Execution task timed out: {task_path}")
    if completed.get("state") not in {"SUCCEEDED", "COMPLETE"}:
        raise RuntimeError(
            f"Luau Execution task failed ({completed.get('state')}): "
            + json.dumps(completed.get("error") or completed, ensure_ascii=False)[-3000:]
        )
    binary_url = str(completed.get("binaryOutputUri") or "")
    if not binary_url:
        raise RuntimeError("Luau Execution task returned no binaryOutputUri")

    summary: dict[str, Any] = {}
    results = nested_dict(completed.get("output")).get("results")
    if isinstance(results, list) and results and isinstance(results[0], str):
        try:
            decoded = json.loads(results[0])
            if isinstance(decoded, dict):
                summary = decoded
        except json.JSONDecodeError:
            summary = {"status": "invalid-summary", "raw": results[0][-1000:]}
    return download_binary(binary_url), summary, task_path


def valid_checkpoint(
    checkpoint: dict[str, Any],
    digest: str,
    settings: dict[str, str],
) -> bool:
    return all(
        (
            checkpoint.get("recipeVersion") == RECIPE_VERSION,
            checkpoint.get("inputSha256") == digest,
            str(checkpoint.get("creatorId") or "") == settings["creatorId"],
            str(checkpoint.get("creatorType") or "") == settings["creatorType"],
            str(checkpoint.get("assetId") or "").isdigit(),
            checkpoint.get("uploadStatus") == "uploaded",
        )
    )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload one arbitrary FBX to Roblox, cloud-LoadAsset it, and save the exact Model as RBXM."
    )
    parser.add_argument("fbx", help="Input .fbx path")
    parser.add_argument("--output", help="Output .rbxm; defaults next to the FBX")
    parser.add_argument("--checkpoint", help="Upload checkpoint JSON; defaults to <output>.upload.json")
    parser.add_argument("--report", help="Completion report JSON; defaults to <output>.report.json")
    parser.add_argument("--config", default="", help="Config JSON; defaults to ROBLOX_UPLOADER_CONFIG")
    parser.add_argument("--creator-id", default="")
    parser.add_argument("--creator-type", choices=["user", "group"], default="")
    parser.add_argument("--universe-id", default="")
    parser.add_argument("--place-id", default="")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--description", default="Uploaded by roblox-fbx-to-rbxm")
    parser.add_argument("--rbxcloud", default="rbxcloud")
    parser.add_argument("--execute", action="store_true", help="Perform upload/task writes; otherwise dry-run")
    parser.add_argument("--force-upload", action="store_true", help="Create a new Model asset even if checkpoint matches")
    parser.add_argument("--poll-ms", type=int, default=2000)
    parser.add_argument("--poll-max", type=int, default=90)
    parser.add_argument("--task-poll-ms", type=int, default=2000)
    parser.add_argument("--task-poll-max", type=int, default=180)
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    fbx = Path(args.fbx).expanduser().resolve()
    if not fbx.is_file():
        parser.error(f"FBX not found: {fbx}")
    if fbx.suffix.lower() != ".fbx":
        parser.error(f"Input must have .fbx extension: {fbx}")

    output = Path(args.output).expanduser().resolve() if args.output else fbx.with_suffix(".rbxm")
    if output.suffix.lower() != ".rbxm":
        parser.error(f"Output must have .rbxm extension: {output}")
    checkpoint_path = (
        Path(args.checkpoint).expanduser().resolve()
        if args.checkpoint
        else Path(str(output) + ".upload.json")
    )
    report_path = (
        Path(args.report).expanduser().resolve()
        if args.report
        else Path(str(output) + ".report.json")
    )
    digest = sha256_file(fbx)
    settings = load_settings(args, strict=args.execute)
    checkpoint = read_json(checkpoint_path) if checkpoint_path.exists() else {}
    reuse = bool(settings["creatorId"]) and valid_checkpoint(checkpoint, digest, settings) and not args.force_upload

    plan = {
        "schema": "roblox-fbx-to-rbxm-plan-v1",
        "mode": "execute" if args.execute else "dry-run",
        "input": str(fbx),
        "inputBytes": fbx.stat().st_size,
        "inputSha256": digest,
        "output": str(output),
        "checkpoint": str(checkpoint_path),
        "report": str(report_path),
        "creatorType": settings["creatorType"],
        "creatorId": settings["creatorId"],
        "universeId": settings["universeId"],
        "placeId": settings["placeId"],
        "apiKeyConfigured": bool(settings["apiKey"]),
        "reuseCheckpointAsset": reuse,
        "wouldUpload": not reuse,
        "wouldRunLuauExecution": True,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.execute:
        return 0

    report: dict[str, Any] = {
        **plan,
        "schema": "roblox-fbx-to-rbxm-report-v1",
        "status": "running",
        "startedAt": now_iso(),
    }
    try:
        if reuse:
            asset_id = str(checkpoint["assetId"])
            print(f"[reuse-upload] modelAssetId={asset_id}", flush=True)
        else:
            print(f"[upload] {fbx}", flush=True)
            asset_id = upload_fbx(args, settings, fbx)
            checkpoint = {
                "schema": "roblox-fbx-to-rbxm-upload-checkpoint-v1",
                "recipeVersion": RECIPE_VERSION,
                "input": str(fbx),
                "inputSha256": digest,
                "creatorType": settings["creatorType"],
                "creatorId": settings["creatorId"],
                "assetId": asset_id,
                "assetUri": f"rbxassetid://{asset_id}",
                "uploadStatus": "uploaded",
                "uploadedAt": now_iso(),
            }
            write_json_atomic(checkpoint_path, checkpoint)
        report["modelAssetId"] = asset_id
        report["modelAssetUri"] = f"rbxassetid://{asset_id}"

        print(f"[cloud-loadasset] modelAssetId={asset_id}", flush=True)
        rbxm, summary, task_path = run_cloud_serialization(args, settings, asset_id)
        if not rbxm.startswith(RBXM_MAGIC):
            raise RuntimeError(f"Cloud output is not a Roblox binary model (bytes={len(rbxm)})")
        if summary.get("status") != "loaded":
            raise RuntimeError("Cloud summary did not confirm loaded Model")
        if str(summary.get("modelAssetId") or "") != asset_id:
            raise RuntimeError("Cloud summary modelAssetId does not match uploaded asset")
        write_bytes_atomic(output, rbxm)

        report.update(
            {
                "status": "complete",
                "completedAt": now_iso(),
                "cloudTaskPath": task_path,
                "outputBytes": len(rbxm),
                "outputSha256": hashlib.sha256(rbxm).hexdigest(),
                "rbxmMagicValid": True,
                "summary": summary,
            }
        )
        write_json_atomic(report_path, report)
        print(f"[complete] {output}")
        print(f"modelAssetId={asset_id} meshParts={summary.get('meshPartCount', 0)} bytes={len(rbxm)}")
        return 0
    except Exception as exc:
        report.update({"status": "failed", "failedAt": now_iso(), "error": str(exc)})
        write_json_atomic(report_path, report)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Failure report: {report_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
