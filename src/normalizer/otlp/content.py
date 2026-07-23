#!/usr/bin/env python3
"""도구 인자에서 파일 경로·명령을 뽑는 유틸 — 경로 구분자는 '/' 로 통일."""
from __future__ import annotations


def _extract_files(payload: dict, keys: tuple[str, ...]) -> list[str]:
    files: list[str] = []
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v:
            files.append(v.replace("\\", "/"))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item:
                    files.append(item.replace("\\", "/"))
    for e in payload.get("edits", []) or []:
        if isinstance(e, dict) and e.get("file_path"):
            files.append(str(e["file_path"]).replace("\\", "/"))
    return files


def _extract_command(payload: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    return None
