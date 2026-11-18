"""Persist observed experiment states without changing model behavior."""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")
    temporary.replace(path)


def update(results: dict) -> None:
    write(ROOT / "results.json", results)
    lines = ["# official-tutorial-v5-dataset: generation token-cap comparison", "",
             "학습 1,024토큰·100스텝, v5 train만 사용. validation의 동일2건으로 비교. test500 사용 없음.", "",
             "| 모델 | ID | 생성 조건 | 실제 생성량 | 종료 | JSON/schema | 라벨 일치 | 상태 |",
             "| --- | --- | --- | ---: | --- | --- | --- | --- |"]
    for r in results["generation"]:
        lines.append(f"| {r['model']} | {r['id']} | {r['budget']} | {r.get('generated_tokens', '—')} | "
                     f"{r.get('stop_reason', '—')} | {r.get('schema_valid', '—')} | {r.get('label_match', '—')} | {r['status']} |")
    lines += ["", f"학습 상태: `{results['training']['status']}`.",
              "", "생성에 외부 시간 제한·강제 EOS·final-prefill을 추가하지 않는다."]
    (ROOT / "results.md").write_text("\n".join(lines) + "\n")
