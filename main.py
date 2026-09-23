def main() -> None:
    # """Print a short project status message."""
    # print(
    #     "AegisLM scaffold is ready. "
    #     "See README.md and docs/FINETUNING_EXPERIMENT_PLAN.md for the roadmap."
    # )

    import json
    from pathlib import Path

    path = Path("data/processed/phase-f-source-v5-r1/train.jsonl")

    with path.open(encoding="utf-8") as f:
        record = json.loads(next(f))

    messages = record["messages"]
    roles = [message["role"] for message in messages]

    assert roles == ["system", "user", "assistant"]

    # 모델에게 주는 문제
    prompt_messages = messages[:-1]

    # 모델이 출력하도록 학습할 정답
    target_text = messages[-1]["content"]
    target = json.loads(target_text)

    print("대화 역할:", roles)
    print("문제 메시지 수:", len(prompt_messages))
    print("정답 필드:", sorted(target))
    print("분석 범위:", target["scope"])
    print("정답 판단:", target["assessment"])

    ### 1. 토크나이저 준비
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        "adapters/source-v2-unsloth-v2/canary/final",
        local_files_only=True,
    )

    ### 2 문제와 전체 대화를 각각 토큰화
    training_messages = prompt_messages + [

    ]
if __name__ == "__main__":
    main()
