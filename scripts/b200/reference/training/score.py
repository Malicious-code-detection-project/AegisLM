"""Rescore returned token IDs using the official Harmony parser, offline from generation.

Keep the literal-matcher result as historical evidence. No model outputs, IDs,
training artifacts, or generation conditions are rewritten.
"""

import importlib.metadata
import json
from collections import Counter

from openai_harmony import (
    HarmonyEncoding,
    HarmonyEncodingName,
    Role,
    TextContent,
    load_harmony_encoding,
)

from common import ROOT, now, write


def score_tokens(
    encoding: HarmonyEncoding, ids: list[int], expected: dict[str, str]
) -> dict[str, object]:
    try:
        messages = encoding.parse_messages_from_completion_tokens(ids, Role.ASSISTANT)
    except Exception as error:
        return {
            "harmony_parse_error": str(error),
            "final_channel_present": False,
            "json_valid": False,
            "schema_valid": False,
            "label_match": False,
            "assessment": None,
            "tool_request": bool(ids and ids[-1] == 200012),
        }
    final_messages = [
        m for m in messages if m.channel == "final" and m.author.role == Role.ASSISTANT
    ]
    tool = bool(ids and ids[-1] == 200012)
    final = (
        "".join(
            content.text
            for content in final_messages[0].content
            if isinstance(content, TextContent)
        )
        if final_messages
        else ""
    )
    parsed = None
    json_valid = False
    try:
        parsed = json.loads(final)
        json_valid = True
    except json.JSONDecodeError:
        pass
    schema = (
        isinstance(parsed, dict)
        and set(parsed) == {"assessment"}
        and isinstance(parsed["assessment"], str)
        and parsed["assessment"] in {"present", "not_observed", "uncertain"}
    )
    return {
        "harmony_parse_error": None,
        "final_channel_present": bool(final_messages),
        "extracted_final": final,
        "parsed": parsed,
        "json_valid": json_valid,
        "schema_valid": schema,
        "label_match": schema and parsed == expected,
        "assessment": parsed["assessment"] if schema else None,
        "tool_request": tool,
        "channels": [m.channel for m in messages],
    }


def main() -> None:
    encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    results = json.loads((ROOT / "results.json").read_text())
    expected = {
        r["id"]: r["expected_output"]
        for r in json.loads((ROOT / "gold.json").read_text())
    }
    corrected = []
    for row in results["generation"]:
        if row["status"] != "completed":
            corrected.append(dict(row))
            continue
        path = ROOT / f"{row['model']}-{row['budget']}-{row['id']}.json"
        detail = json.loads(path.read_text())
        corrected.append(
            {
                **row,
                "literal_matcher": {
                    key: row[key]
                    for key in [
                        "final_channel_present",
                        "json_valid",
                        "schema_valid",
                        "label_match",
                        "assessment",
                    ]
                },
                **score_tokens(encoding, detail["generated_ids"], expected[row["id"]]),
            }
        )
    groups = []
    for model in ["base", "adapter"]:
        for budget in [128, 512, 2048, 65536, "context-minus-input"]:
            rows = [
                r for r in corrected if r["model"] == model and r["budget"] == budget
            ]
            done = [r for r in rows if r["status"] == "completed"]
            matrix = Counter()
            for row in done:
                if not row["schema_valid"]:
                    matrix["invalid"] += 1
                elif row["assessment"] == "uncertain":
                    matrix["uncertain"] += 1
                else:
                    source = expected[row["id"]]["assessment"]
                    matrix[
                        ("TP" if source == "present" else "FP")
                        if row["assessment"] == "present"
                        else ("FN" if source == "present" else "TN")
                    ] += 1
            groups.append(
                {
                    "model": model,
                    "budget": budget,
                    "completed": len(done),
                    "final": sum(r["final_channel_present"] for r in done),
                    "schema": sum(r["schema_valid"] for r in done),
                    "label_match": sum(r["label_match"] for r in done),
                    "native_eos": sum(r["stop_reason"] == "native_eos" for r in done),
                    "token_limit": sum(r["stop_reason"] == "token_limit" for r in done),
                    "tool_requests": sum(r["tool_request"] for r in done),
                    "generated_tokens": [r["generated_tokens"] for r in done],
                    "confusion": {
                        key: matrix[key]
                        for key in ["TP", "TN", "FP", "FN", "invalid", "uncertain"]
                    },
                }
            )
    report = {
        "experiment_id": ROOT.name,
        "scored_at": now(),
        "parser": "openai-harmony",
        "parser_version": importlib.metadata.version("openai-harmony"),
        "generation_completed": sum(r["status"] == "completed" for r in corrected),
        "generation_total": 20,
        "rows": corrected,
        "groups": groups,
        "test_used": False,
    }
    write(ROOT / "scored-results.json", report)
    lines = [
        "# official-tutorial-v5-dataset: corrected Harmony evaluation",
        "",
        "원 token IDs를 official openai-harmony parser로 평가했다. 학습·생성·원문은 수정하지 않았다.",
        "literal final-marker 검사도 원 results.json에 보존한다.",
        "",
        "| 모델 | 생성 상한 | 완료 | final | JSON/schema | 원천 라벨 일치 | EOS / 상한 | tool request | 실제 생성량 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for row in groups:
        lines.append(
            f"| {row['model']} | {row['budget']} | {row['completed']}/2 | {row['final']} | {row['schema']} | {row['label_match']} | "
            f"{row['native_eos']} / {row['token_limit']} | {row['tool_requests']} | {row['generated_tokens']} |"
        )
    lines += [
        "",
        "동일 validation2건 진단이다. uncertain·형식 실패는 TP/TN/FP/FN과 분리한다. test500 성능으로 일반화하지 않는다.",
    ]
    (ROOT / "scored-results.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "rows"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
