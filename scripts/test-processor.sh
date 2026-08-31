#!/usr/bin/env bash
# telemetry-processor 테스트 러너 (Docker python:3.13-slim).
#
# 호스트 python 이 3.13 이 아니어도 CI 와 같은 인터프리터로 돌리기 위한 스크립트다.
# 러너는 stdlib unittest 이며 테스트 전용 의존성이 없다 — requirements.txt 는
# 런타임 의존성 전용이라 psycopg 만 설치한다(enrichment.providers.org 가 import).
#
# 인자는 그대로 `python -m unittest` 에 넘어간다.
#   scripts/test-processor.sh                             # 전체
#   scripts/test-processor.sh tests.normalizer.test_golden_claude_code_logs
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PYTHON_IMAGE:-python:3.13-slim}"
PIP_CACHE="${REPO_ROOT}/.cache/pip"

mkdir -p "${PIP_CACHE}"

if [[ $# -gt 0 ]]; then
  UNITTEST_ARGS=("$@")
else
  UNITTEST_ARGS=(discover -s tests -t . -v)
fi

# -t . 로 top-level 을 앱 루트에 고정한다. 프로덕션 코드가 `from normalizer import ...`
# 절대 import 를 쓰므로 sys.path[0] 이 apps/telemetry-processor 여야 한다.
exec docker run --rm \
  -v "${REPO_ROOT}:/w" \
  -v "${PIP_CACHE}:/root/.cache/pip" \
  -w /w/apps/telemetry-processor \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "${IMAGE}" \
  sh -ec '
    pip install --quiet --root-user-action=ignore -r requirements.txt
    exec python -m unittest "$@"
  ' -- "${UNITTEST_ARGS[@]}"
