# v4.0 기능별·모델 교체형 하네스 — 전환과 검증

작성일: **2026-09-30**. 입력은 이 대화의 `task_success_harness_v3_integrated.zip`이다. 새 묶음을 별도 경로에 만들었으며 사용자 저장소·전역 설정·기존 ZIP은 수정하지 않았다. 별도 모델 호출이나 독립 검토를 수행한 결과가 아니다.

## 1. 설계 변경

메인이 공동 목표·성공 기준·통합을 유지한다. 역할은 explorer/planner/patcher/reviewer/tester의 전문 기능이며 모델은 DEFAULT/FAST/DEEP 슬롯으로 분리한다. 기본 제안은 Sol 6.1, 중요한 난제는 조건부 Astra다. 타사 모델은 같은 역할을 맡길 후보이며 동급 성능을 전제하지 않는다.

[공개 사례 조사](reference/cases.md)에 Pi 공식 예제, OpenCode Slim, Oh My Pi, 사용자 프리셋 사례와 공식 연결 근거를 구분했다. 그대로 설치하거나 외부 프롬프트 전문을 복제하지 않았다. [모델 운영표](core/models.md)는 배정 제안, [실행 연결](adapters/runtime.md)은 실제 모델·도구·권한 확인 기준이다. 둘 다 런타임 설정 파일이 아니다.

| 이전 업무 | v4에서 맡는 위치 |
| --- | --- |
| Astra의 목표 유지·통합 | 현재 메인 세션; 별도 관리자 호출 없음 |
| Astra의 중요한 연구·설계 | 필요 시 planner 또는 DEEP 판단 |
| Sol의 조사·방법론·독립 검토 | explorer / planner / reviewer의 해당 모드 |
| Terra의 구현·디버깅 | patcher / 허용된 tester-repair |
| Luna의 위치 조사·실행 기록 | explorer / tester-verify |

작업을 다섯 단계로 강제하지 않는다. tester는 verify가 기본이며 제품 수정은 지정된 repair 범위에만 허용한다. 검토·실행 근거는 후보 버전과 연결하고 수정 후 영향받은 검증만 갱신한다. 역할별 파일에 모델명을 넣지 않아 모델을 교체해도 역할 명세는 유지된다.

## 2. 보존한 기준과 지식

| 기준 | 현재 문서 |
| --- | --- |
| 공동 성공·미검증·부정 결과·권한 | 공통 원칙 |
| 실제 원본·조건·실패·후보별 근거 | 공통 원칙 + 역할 반환 + task |
| 연구 비교·누수·최종 평가 보호 | workflow + planner + reviewer |
| 작성 참여·별도 맥락·근거를 보는 검토 | 공통 원칙 + reviewer |
| 쓰기 순서·repair 제한·반복 중단 | workflow + patcher + tester |
| 모델과 역할 분리·연결 미확인·제공자 전송 | models + runtime |
| Wiki 선택 조회·단일 편집·새 지식만 반영 | 기존 통합 지식 운영 절차 |

`raw/` 3개 파일, Wiki 출처 요약 2개, Wiki 페이지 템플릿 1개를 v3와 바이트 동일하게 보존했다. Karpathy 공개 최신본·라이선스·원문의 정확성을 이번에 재검증한 것은 아니다. 원문 SHA-256은 아래에 있다.

Wiki는 기존 OKF 0.2 운영 범위를 유지한다. 이번에는 새 사양 탐색·변경이나 OKF 인증을 수행하지 않았다. 통합 결정과 인덱스 설명·제작 로그만 새 역할에 맞췄다. 실제 B200·vLLM·모델 평가 수치를 만들거나 입력하지 않았다.

### v3 보존 이력에 대한 참조

보존된 `raw/karpathy/SOURCE.md`의 v2/v3 확인 서술은 당시 기록이다. 이 파일의 기존 링크는 현재 `REFACTOR.md`로 이어진다. v3의 전체 제작·측정 원문은 입력 v3 ZIP의 같은 경로에 그대로 있다. 현행 v4 문서가 v3 당시 실험을 다시 실행했다는 뜻이 아니다. 이전 Wiki 로그의 v3 항목도 원본 ZIP의 제작 이력을 가리키도록 정리했다.

## 3. 기존 프로젝트로 반영

압축은 기존 프로젝트 밖의 별도 폴더에 먼저 푼다. 적용 전에 실제 사용자 수정과 팀 규칙을 비교한다. 이 배포물은 자동 설치·삭제·마이그레이션을 하지 않는다.

| 범위 | 반영 원칙 |
| --- | --- |
| README / core / 역할 | 새 역할과 모델표를 함께 검토해 교체·병합한다. 기존 모델 역할과 새 역할을 동시에 활성 규칙으로 쓰지 않는다. |
| 이전 astra/sol/terra/luna 링크 | 실제 사용자 문서에서 역참조를 확인한다. 기록상 이름은 바꾸지 않는다. 필요한 안내 문서는 새 역할을 가리키되 옛 규칙을 다시 로딩하지 않는다. |
| 모델·권한 설정 | 현재 앱의 실제 설정을 확인한다. 별도 허용 없이 TOML/JSON·루트·전역 설정을 만들거나 바꾸지 않는다. |
| 진행 중 tasks | 단일 task든 기존 5파일이든 그대로 이어간다. 역할 이력·검증·모델 식별자를 과거로 소급 수정하지 않는다. |
| raw / Wiki 본문 / index / log | 실제 사용자 지식을 초기 파일로 덮어쓰지 않는다. 바뀐 설계 결정·탐색 설명·제작 이력만 필요한 경우 병합한다. |
| 이전 보고서 | 원본 v3 ZIP에 보존한다. 새 지침의 기본 입력으로 넣지 않는다. |

현재 사용자 저장소의 역참조·추가 파일·실행 환경은 읽지 않았으므로 실제 병합 충돌이 없다고 보증하지 않는다. 설정이 지원하지 않는 모델을 문서에 적는 것만으로 연결되지 않는다. 필수 검토가 없을 때 자기 검토를 독립 검토로 꾸미지 않는다.

## 4. 문서 분량 — 실제 문자 측정

| 측정 | v3 | v4 |
| --- | ---: | ---: |
| Markdown 파일 | 19 | 24 |
| 전체 보관 문서 | 37,921자 | 48,600자 |
| 검증된 프로필의 새 과업 기본 시작 | 4,486자 | 4,118자 |
| 위 기본 시작 + 운영 절차 | 6,555자 | 6,068자 |
| 새 프로필 최초 확인 — v4 모델표·연결 문서 포함 | 비교 항목 없음 | 8,476자 |

기본 시작 v3는 README+공통 원칙+Astra+빈 task, v4는 README+공통 원칙+빈 task다. v4 메인 조율 규칙은 README에 있으므로 없앤 것이 아니라 위치를 바꿨다. 각 전문 역할 수행 시 해당 역할 문서를 별도 읽는다. 실제로 모델표·연결 문서를 다시 읽었으면 사용량에서 제외하지 않는다.

문자 수는 UTF-8 문서를 해독한 Python `len(text)`이며 공백·줄바꿈·메타데이터를 포함한다. 실제 원자료·도구 출력·패킷·모델 생성·캐시·추론 토큰은 포함하지 않는다. 기본 시작 문서는 약 8.2% 줄었지만 **최초 연결 비용은 추가됐고, 전체 참고 문서도 늘었다**. 이 비율은 토큰·과금·시간 절감률이 아니다. v3보다 모든 조건에서 가벼워졌다고 해석하지 않는다.

모델별·플랫폼별 운용을 설명하는 참고 문서는 기본 입력에서 제외한다. 이 제외는 실제 읽기 경로 설계이지 자동 로더가 아니며 실제 비용은 로그로 확인해야 한다.

## 5. 이번에 실제 수행한 검사

| 검사 | 결과·범위 |
| --- | --- |
| 배포 형식 | Markdown 24개, 비Markdown·심볼릭 링크 없음 |
| 역할 구성 | 다섯 기능 파일만 존재; 역할 본문에 모델 이름 없음 |
| 기본/전문 읽기 경로 | 연결된 로컬 링크 51개 대상 존재 확인 |
| 외부 링크 | 고유 URL 21개 문법 확인; 모든 URL의 영구 가용성을 보증하지 않음 |
| Wiki 형식 | 실제 지식 3개 frontmatter와 index의 0.2 표시 파싱; verified 생성 없음 |
| Wiki 출처 | 로컬 4개 대상 존재; 외부 1개 URL 형식 확인 |
| 각주·주장 앵커 | 문서별 출처 각주 ID 5개 연결; 기존 앵커 7개 보존 |
| 파일 보존 | 위 6개 파일의 바이트가 입력 v3와 동일 |
| Wiki 템플릿 | 6개 깊이/주제 위치에 임시 복사; 형식·고정 상대 링크 부재 확인 |
| 과업 템플릿 | 임시 task 경로에 복사; 위치 종속 링크 없음 |
| UTF-8 / 빈 파일 / 코드 펜스 | 검사 통과 |
| ZIP | CRC 무결성·포함 경로·빈 폴더·파일별 바이트 동일성 검사 통과 |
| 원본 입력 | v3 ZIP 해시 불변 확인 |

이것은 제작 환경의 정적 검사와 수동 규칙 점검이다. 모델이 실제로 권한을 지키는지 시험한 결과나 독립 에이전트의 검토가 아니다. 템플릿 임시 복사는 경로 문제를 확인할 뿐 연구·코딩 능력을 검증하지 않는다.

**미실행:** Codex/OpenCode/Pi/Claude 앱 설치·네이티브 등록, 실제 자식 세션 모델/권한·API 왕복, 타사 계정·구독 접근, 모델별 역할 적합성, 사용자 WSL·프로젝트 테스트, 실험 설계 정확성, 실제 비용·시간·재작업 감소. 다음 검증은 [EVALUATION.md](EVALUATION.md)의 동일 과업 비교를 사용한다.

## 6. 입력과 보존 해시

입력 `task_success_harness_v3_integrated.zip` SHA-256:
`138feeb2d12f93aa217aa256429885b3b5e17097d35dedec3325557d050885c4`

보존 `raw/karpathy/llm-wiki.md` SHA-256:
`d1c5f89f21fc8f2671f0c5479ccfaadfbca1ce9fb441867172d0852529861169`

## 7. 파일별 문자 수

| 파일 — references/이정민 기준 | 문자 |
| --- | ---: |
| `harness/EVALUATION.md` | 1,926 |
| `harness/README.md` | 1,602 |
| `harness/REFACTOR.md` | 5,665 |
| `harness/adapters/runtime.md` | 2,271 |
| `harness/core/models.md` | 2,087 |
| `harness/core/principles.md` | 1,611 |
| `harness/core/workflow.md` | 1,950 |
| `harness/playbooks/llm-wiki.md` | 2,496 |
| `harness/reference/cases.md` | 4,602 |
| `harness/roles/explorer.md` | 625 |
| `harness/roles/patcher.md` | 603 |
| `harness/roles/planner.md` | 619 |
| `harness/roles/reviewer.md` | 699 |
| `harness/roles/tester.md` | 881 |
| `harness/tasks/_template/task.md` | 905 |
| `harness/templates/wiki-page.md` | 474 |
| `raw/README.md` | 451 |
| `raw/karpathy/SOURCE.md` | 2,036 |
| `raw/karpathy/llm-wiki.md` | 11,996 |
| `wiki/decisions/harness-wiki-integration.md` | 1,235 |
| `wiki/index.md` | 528 |
| `wiki/log.md` | 902 |
| `wiki/sources/google-open-knowledge-format.md` | 1,305 |
| `wiki/sources/karpathy-llm-wiki.md` | 1,131 |


## AegisLM 로컬 적용 — 2026-10-02

- 사용자 요청으로 `~/Desktop/AegisLM_Architecture`의 공통 v4 하네스 16개 파일을 가져왔다.
  원본 저장소 HEAD: `b3e09a49e96eb4153d74d24b5464b2e56a2f7239`; 복사 당시 작업 트리는 clean이었다.
- 원본의 제작·검증 기록은 위 본문에 보존했다. 그 기록을 이 저장소에서 재실행한 것으로 보지 않는다.
- Architecture의 `tasks/cwe-selective-block-adaptation/`은 제외했고 이 저장소의 원자료와 기존 과업은 보존했다.
- v3 역할 문서 4개, skill router, 로컬 에이전트 TOML 7개, `.harness-local/jeongmin/`의 이전 생성 설정을 제거했다.
  루트 `AGENTS.md`, 프로필 인덱스, Wiki의 현행 역할 설명, 문서 진입 링크를 v4에 맞췄다.
- 사용자 선택 모델과 실제 도구 권한이 기준이다. 원본 `core/models.md`의 후보를 자동 적용하거나
  새 네이티브 에이전트를 등록하지 않았다. 전역 설정과 원본 저장소는 수정하지 않았다.
- 교체 전 사본 및 변경 manifest는 Git 제외 `outputs/harness-migration-20261002/`에 있다.
  SHA 검증과 로컬 링크·구형 경로 부재 검사를 수행한다. 검증 결과는 같은 manifest에 기록한다.
- 이번 작업은 문서·라우팅 정리다. 모델별 역할 성능·하위 모델 실행·GPU 학습 검증을 수행한 결과가 아니다.
