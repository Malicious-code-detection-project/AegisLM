# Quality Gates

이 문서는 `AegisLM` 코드 변경 PR에서 실행해야 하는 기본 검사 기준을 정의합니다.

Phase D부터 baseline inference, prompt formatting, evaluation, training helper 같은 Python 코드가 늘어나므로 기본 검사를 `pytest`, `ruff`, `mypy`로 고정합니다.

## 1. Required Commands

코드 변경 PR은 가능한 범위에서 다음 명령을 실행합니다.

```bash
uv run pytest tests/
uv run ruff check .
uv run ruff format --check .
uv run mypy aegislm/ tests/
```

각 명령의 책임은 다릅니다.

| Command | Purpose |
| --- | --- |
| `uv run pytest tests/` | unit test와 fixture 기반 동작 검증 |
| `uv run ruff check .` | lint, unused import, 버그성 패턴 검사 |
| `uv run ruff format --check .` | formatter 기준 준수 여부 확인 |
| `uv run mypy aegislm/ tests/` | type hint 기반 정적 타입 검사 |

문서만 변경하는 PR은 코드 검사를 생략할 수 있지만, PR 본문에 생략 사유를 적습니다.

## 2. pytest Policy

테스트는 `pytest` runner와 pytest-style function/assert를 기본으로 작성합니다. 새 테스트와 기존 테스트 수정은 `unittest.TestCase`, `unittest.main()`, `self.assert*` 패턴을 추가하지 않습니다.

테스트는 다음 기준을 따릅니다.

- 동작 검증은 `tests/` 아래에 둔다.
- fixture 파일은 `tests/fixtures/` 아래에 둔다.
- temporary file/directory는 가능한 경우 pytest `tmp_path` fixture를 사용한다.
- exception 검증은 `pytest.raises(..., match=...)`를 사용한다.
- 반복 입력 검증은 plain loop assertion 또는 `pytest.mark.parametrize`를 사용한다.
- prompt 변경은 message shape, required instruction, safety instruction을 확인한다.
- evaluation 변경은 invalid JSON, missing field, hallucinated mapping, unsafe guidance를 확인한다.

## 3. mypy Policy

mypy는 `aegislm/`와 `tests/`를 검사합니다.

초기 정책은 strict mode가 아닙니다. 목표는 구현 속도를 막지 않으면서 다음 오류를 조기에 찾는 것입니다.

- 잘못된 return type
- `None` 가능성 누락
- fixture record의 잘못된 dict/list 접근
- public helper의 type hint 불일치

strict mode, coverage 증가, third-party typing 정책 강화는 별도 이슈에서 다룹니다.
