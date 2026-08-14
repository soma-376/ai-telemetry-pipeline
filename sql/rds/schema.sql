-- RDS(mock) 조직 스키마. compose 가 /docker-entrypoint-initdb.d 로 마운트해
-- 최초 초기화 시 자동 적용한다(01-schema → 02-seed 순). 볼륨이 없으므로
-- down 후 up 마다 재적용된다(결정론적 리셋 — 권위 소스는 이 파일).
-- 조직 배치는 유효기간(effective-dated) assignment 로 모델링 → 이력 규칙(소급 변경 금지) 충족.

DROP TABLE IF EXISTS employee_department_assignment CASCADE;
DROP TABLE IF EXISTS department CASCADE;
DROP TABLE IF EXISTS employee CASCADE;
DROP TABLE IF EXISTS company CASCADE;

CREATE TABLE company (
    id   text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE department (
    id         text PRIMARY KEY,
    company_id text NOT NULL REFERENCES company(id),
    code       text NOT NULL,
    name       text NOT NULL,
    UNIQUE (company_id, code)
);

CREATE TABLE employee (
    id         text PRIMARY KEY,
    company_id text NOT NULL REFERENCES company(id),
    email      text NOT NULL,
    name       text NOT NULL
);

-- 유효구간 [valid_from, valid_to) 반열림. valid_to IS NULL = 현재까지 유효.
CREATE TABLE employee_department_assignment (
    employee_id   text NOT NULL REFERENCES employee(id),
    department_id text NOT NULL REFERENCES department(id),
    valid_from    date NOT NULL,
    valid_to      date,
    PRIMARY KEY (employee_id, valid_from)
);
