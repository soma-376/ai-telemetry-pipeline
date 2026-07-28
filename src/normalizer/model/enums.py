#!/usr/bin/env python3
"""enum (event.proto 미러) — 순수 상수, 로직 없음."""

from __future__ import annotations

from enum import Enum


class Surface(str, Enum):
    UNKNOWN = "unknown"
    CLI = "cli"
    IDE = "ide"
    WEB_EXT = "web_ext"
    API = "api"
    CI = "ci"


class SignalType(str, Enum):
    """어느 OTel 신호에서 왔는가. read_all 이 resourceLogs/Spans/Metrics 로 분기해
    LOG/SPAN/METRIC 을 스탬프한다. 조인은 이 값이 아니라 join_id 로 한다."""

    LOG = "log"
    METRIC = "metric"
    SPAN = "span"


class ValueSource(str, Enum):
    REPORTED = "reported"  # 툴이 직접 제공 (CC 의 cost_usd)
    ESTIMATED = "estimated"  # pricing 표로 계산


class LogKind(str, Enum):
    """로그 = 점(event). '무슨 일이 일어났다'는 순간 사실."""

    USER_PROMPT = "user_prompt"
    LIFECYCLE = "lifecycle"

    LLM_CALL = "llm_call"
    LLM_RESPONSE = "llm_response"  # 모델 응답 완료 또는 assistant message

    TOOL_CALL = "tool_call"
    TOOL_DECISION = "tool_decision"

    OTHER = "other"


class SpanKind(str, Enum):
    """스팬 = 구간(interval). type 이 곧 역할이다 (span_role 흡수). CC 스팬명 기준."""

    TURN = "turn"  # claude_code.interaction
    LLM_REQUEST = "llm_request"  # claude_code.llm_request
    TOOL = "tool"  # claude_code.tool (권한대기+실행 포함 전체 구간)
    TOOL_GATE = "tool_gate"  # claude_code.tool.blocked_on_user (승인 대기)
    TOOL_EXECUTION = "tool_execution"  # claude_code.tool.execution (본문 실행)
    HOOK = "hook"  # claude_code.hook (베타·게이트)

    OTHER = "other"


class ToolKind(str, Enum):
    UNKNOWN = "unknown"
    NATIVE = "native"
    MCP = "mcp"
    SKILL = "skill"
    SUBAGENT = "subagent"
    EXTENSION = "extension"
    API = "api"
    CUSTOM = "custom"


# 툴이 어떤 작업을 수행했는가
class ToolAction(str, Enum):
    OTHER = "other"

    READ = "read"  # 파일/문서 읽기
    SEARCH = "search"  # grep, glob, web search

    WRITE = "write"  # 새 파일 생성
    EDIT = "edit"  # 기존 파일 수정
    DELETE = "delete"  # 삭제

    EXEC = "exec"  # bash, python 실행
    FETCH = "fetch"  # API/MCP 호출, 외부 데이터 조회

    GENERATE = "generate"  # 이미지, 문서, 초안 생성


class Decision(str, Enum):
    """Tool 실행 요청에 대해 내려진 최종 결정.
    (예: 승인, 거부, 수정 후 승인, 실행 중단)
    """

    UNKNOWN = "unknown"
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"
    ABORT = "abort"


# 누가 또는 무엇이 결정했는가
class DecisionSource(str, Enum):
    UNKNOWN = "unknown"
    USER = "user"
    CONFIG = "config"
    HOOK = "hook"
    POLICY = "policy"
    SYSTEM = "system"


# 결정이 어디까지, 얼마나 오래 적용되는가
class DecisionScope(str, Enum):
    UNKNOWN = "unknown"
    ONCE = "once"
    SESSION = "session"
    PROJECT = "project"
    WORKSPACE = "workspace"
    PERMANENT = "permanent"
