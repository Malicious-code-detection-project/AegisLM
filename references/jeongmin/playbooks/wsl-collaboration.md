# Playbook · WSL과 대형 팀의 병렬 작업

각 팀원의 개인 폴더는 **자료 분리**다. 소스 편집 충돌과 실행 부작용까지 격리하지는 않는다.
WSL 작업 사본에서도 기존 dirty changes와 현재 branch를 먼저 확인한다.

## 한 작업 사본

기본 writer는 하나다. Sol이 쓴 파일/모듈 소유권을 task packet에 기록한다.
다른 팀원 또는 다른 에이전트의 실행 여부를 모르면 잠금을 확인하거나 별도 사본에서 작업한다.
모든 writer의 상태를 알고 있다는 가정으로 '문제없다'고 선언하지 않는다.

## 여러 worktree

팀에서 허용하고 branch 이름이 충돌하지 않는지 확인한 후, 예를 들어 다음과 같이 만든다.
아래는 사용자가 검토 후 실행하는 예시이며 제공 도구가 자동 실행하지 않는다.

```bash
git status --short
git worktree list
# 새 branch/경로인지 확인한 뒤에만 실행한다.
git worktree add ../project-feature-a -b feature/jeongmin-feature-a
```

새 worktree의 `.active-profile`과 `.harness-local/`은 별도로 설정한다.
원본 사본의 untracked/ignored 개인 설정이 자동 복사된다고 가정하지 않는다.
각 작업의 base commit, 후보 diff, 쓰기 범위, 통합 담당자를 기록한다.
worktree는 보안 sandbox가 아니다. 같은 계정/호스트 자원·네트워크·비밀정보 접근을 자동 격리하지 않는다.

## 공유 자원

테스트 DB/schema, 서비스 포트, GPU, 캐시, 출력 경로를 작업별로 분리한다.
특히 B200 실험/모델 서빙과 프로젝트 테스트가 같은 GPU를 쓰면 예약·메모리 여유·프로세스 소유자를 확인한다.
다른 사람이 돌리는 프로세스를 종료하거나 방화벽/운영 설정을 바꾸지 않는다.

## 합치기

단일 통합 담당자가 결과를 검토한다. 같은 파일·생성물·lockfile 충돌은 조용히 덮어쓰지 않는다.
통합된 새 후보에 대해 영향을 받는 검증과 리뷰를 다시 한다.
PR/merge/배포는 팀 정책에 따른다. 하네스의 ACCEPT만으로 자동 push/merge하지 않는다.
