#!/usr/bin/env python3
"""Codex 어댑터 공통 신원 — 세 시그널이 공유.

Codex 는 벤더 이메일·계정을 거의 안 주므로, 정본 신원(user_id)은 온보딩 때 회사가
박은 resource 속성에 의존한다. 벤더 값은 있으면 정보성으로만 채운다.
"""
from __future__ import annotations

from ...model import Client, Identity, Surface
from ...otlp import _opt_str

PREFIX = "codex."
ADAPTER = "codex"
ADAPTER_VERSION = 2


def build_identity(res_attrs: dict, attrs: dict, tenant_id: str | None) -> Identity:
    return Identity(
        tenant_id=tenant_id,
        # 정본 신원 = 온보딩 때 회사가 박은 resource 속성. 없으면 None(미귀속).
        user_id=_opt_str(res_attrs, attrs, keys=("developer.email", "developer.id")),
        # 벤더가 준 신원 — 정보성(정본 아님).
        vendor_email=_opt_str(attrs, res_attrs, keys=("user.email",)),
        vendor_account_id=_opt_str(attrs, res_attrs, keys=("user.account_id",)),
    )


def build_client(res_attrs: dict, attrs: dict) -> Client:
    return Client(
        product="codex",
        surface=Surface.CLI,
        version=_opt_str(attrs, res_attrs, keys=("app.version",)),
    )
