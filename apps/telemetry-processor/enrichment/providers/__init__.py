"""외부 종속성 엔리치먼트 provider 패키지.

새 provider 는 이 패키지에 파일만 추가하면 registry 가 자동 발견한다(코어 수정 0).
공통 컬럼 승격 금지(PLAN §8): provider 산출물은 annotations(→ enrichment_json)로만 적재.
org 만 예외적으로 whitelist 컬럼을 채우는 레퍼런스 구현.
"""
