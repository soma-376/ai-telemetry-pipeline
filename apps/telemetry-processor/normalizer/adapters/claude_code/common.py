#!/usr/bin/env python3
"""Claude Code 어댑터 공통 신원 — 세 시그널(logs/metrics/traces)이 공유.

identity/client 추출은 로그든 메트릭이든 동일하다. 시그널별 파일에 복붙하지 않고
여기 한 곳에 둔다. PREFIX/ADAPTER/ADAPTER_VERSION 도 플랫폼 상수라 여기 둔다.
"""

from __future__ import annotations

from ...model import Client, Identity, Surface
from ...otlp import _opt_str

PREFIX = "claude_code."
ADAPTER = "claude_code"
ADAPTER_VERSION = 3


def build_identity(res_attrs: dict, attrs: dict, tenant_id: str | None) -> Identity:
    return Identity(
        tenant_id=tenant_id,
        # 온보딩 때 회사가 박은 신원(자기신고). 없으면 None(미귀속).
        member_id=_opt_str(res_attrs, attrs, keys=("developer.email", "developer.id")),
        # 프록시가 검증해 collector 가 resource 속성으로 심는 신뢰 키(정본).
        # 속성명은 collector 매핑과 합의 필요(현재 placeholder: developer.installation_id).
        installation_id=_opt_str(res_attrs, attrs, keys=("developer.installation_id",)),
        # 벤더가 준 신원 — 정보성(정본 아님). 섀도우 AI 탐지용.
        vendor_email=_opt_str(attrs, res_attrs, keys=("user.email",)),
        vendor_account_id=_opt_str(
            attrs, res_attrs, keys=("user.account_uuid", "user.account_id")
        ),
    )


def build_client(res_attrs: dict, attrs: dict) -> Client:
    return Client(
        product="claude_code",
        surface=Surface.CLI,
        version=_opt_str(attrs, res_attrs, keys=("app.version", "service.version")),
    )
