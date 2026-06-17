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

기존 테스트가 `unittest.TestCase` 스타일이어도 `pytest`로 실행합니다. `pytest`는 unittest 테스트를 그대로 수집할 수 있으므로, 당장 테스트 전체를 pytest fixture 스타일로 리팩터링하지 않습니다.

새 테스트는 다음 기준을 따릅니다.

- 동작 검증은 `tests/` 아래에 둔다.
- fixture 파일은 `tests/fixtures/` 아래에 둔다.
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

## 4. apply_patch Status

현재 Codex의 `apply_patch` tool은 이 환경에서 다음 오류로 실패합니다.

```text
fs sandbox helper failed with status exit status: 1: bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

판단:

- patch 내용이나 AegisLM 파일 구조 문제가 아니다.
- repo 안의 Python 설정, dependency, test 설정으로 해결할 수 있는 문제가 아니다.
- `bubblewrap` 기반 sandbox가 loopback network namespace를 설정하는 단계에서 권한 문제로 실패한다.

현재 대응:

1. 수동 편집이 필요하면 먼저 `apply_patch`를 시도한다.
2. 같은 bwrap 오류가 재현되면 승인된 shell에서 대상 파일만 제한적으로 수정한다.
3. 수정 후 반드시 `git diff`, `git diff --check`, quality gate 명령으로 검증한다.

근본 해결은 Codex 실행 환경의 sandbox/bwrap 권한 조정이 필요합니다.
