"""telemetry-processor 특성화 테스트 스위트.

현행 동작을 있는 그대로 고정한다(characterization test). Kotlin 이식(PROJ-74)의
회귀 안전망이 목적이므로, 이상해 보이는 동작도 여기서 바꾸지 않고 그대로 묶는다.

실행은 `scripts/test-processor.sh`(Docker python:3.13-slim)를 쓴다. 호스트에서
직접 돌릴 때는 `apps/telemetry-processor` 를 작업 디렉터리로 두어야 한다 —
프로덕션 코드가 `from normalizer import ...` 형태의 절대 import 를 쓰기 때문이다.
"""
