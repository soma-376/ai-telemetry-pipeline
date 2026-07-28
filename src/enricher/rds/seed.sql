-- RDS 결정론적 시드 (PLAN §결정론 상수).
-- emp-404 는 의도적으로 employee 에 넣지 않는다(미등록).
-- emp-002 는 assignment 2행: backend [.., 2026-06-01) → platform [2026-06-01, NULL). 인접(겹침·공백 없음).

INSERT INTO company (id, name) VALUES
  ('acme',   'ACME Corp'),
  ('globex', 'Globex Inc');

INSERT INTO department (id, company_id, code, name) VALUES
  ('acme-platform', 'acme',   'platform', 'Platform'),
  ('acme-backend',  'acme',   'backend',  'Backend'),
  ('globex-data',   'globex', 'data',     'Data');

INSERT INTO employee (id, company_id, email, name) VALUES
  ('emp-001', 'acme',   'alice@acme.test',  'Alice'),
  ('emp-002', 'acme',   'bob@acme.test',    'Bob'),
  ('emp-003', 'globex', 'carol@globex.test','Carol');
  -- emp-404: 없음(미등록)

INSERT INTO employee_department_assignment (employee_id, department_id, valid_from, valid_to) VALUES
  ('emp-001', 'acme-platform', DATE '2020-01-01', NULL),
  ('emp-002', 'acme-backend',  DATE '2020-01-01', DATE '2026-06-01'),
  ('emp-002', 'acme-platform', DATE '2026-06-01', NULL),
  ('emp-003', 'globex-data',   DATE '2020-01-01', NULL);
