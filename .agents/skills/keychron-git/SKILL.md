---
name: keychron-git
description: Use when the user invokes $keychron-git or asks to commit, split commits, write commit or merge messages, clean history, rebase/cherry-pick, prepare the orca-keychron branch for PR, write PR title/body, or create, update, or merge a PR.
---
# Keychron Git

개인 오픈소스 프로젝트 `KMGeon/orca-keychron`의 커밋·PR·merge를 관리한다.

## 작업 범위

- Git 상태 분석, 스테이징, 커밋, 브랜치 정리, 리베이스, 체리픽, PR 준비·생성·갱신과 명시적으로 요청된 merge를 수행한다.
- 기능 코드는 사용자가 함께 요청한 경우에만 수정한다.
- 커밋, 푸시, 리베이스처럼 저장소 상태가 바뀌는 작업은 사용자의 요청 범위 안에서만 수행한다.
- 무관한 사용자 변경을 스테이징하거나 되돌리지 않는다.
- `main`, `master` 브랜치는 리베이스하지 않는다.
- 강제 푸시가 명시적으로 필요한 경우에도 `--force-with-lease`만 사용한다.

## 저장소 확인

- 기본 대상은 `https://github.com/KMGeon/orca-keychron`이다. 쓰기 전에 `git remote -v`와 현재 브랜치를 확인한다.
- 원격이 다른 저장소나 fork를 가리키면 대상만 확인하고 임의로 원격 URL을 변경하지 않는다.
- PR·merge·릴리스는 각각 요청 범위 안에서 수행한다. `main`에 반영하면 자동 릴리스가 시작되는 현재 workflow를 고려한다.
- PR 설명과 References에는 이 프로젝트와 관련된 공개 자료만 사용한다. 회사 내부 링크·티켓·연락처를 가져오지 않는다.

## 저장소 구조

이 프로젝트는 하나의 Git 저장소다. 주요 영역은 다음과 같다.

- `src/orca_keychron/`: Python CLI, Orca 상태 추적, Keychron HID, 렌더링
- `assets/`, `README.md`, `README.ko.md`: 이미지와 사용자 안내
- `tests/`: Python 테스트
- `docs/`, `.agents/skills/`: 문서와 프로젝트 스킬
- `.github/workflows/`: CI와 배포

서브모듈 전용 절차를 적용하지 않는다. 작업 시작 시 루트에서 상태와 변경 범위를 확인한다.

```bash
git status --short --branch
git diff --stat
git diff
git diff --cached
```

## 기본 워크플로

PR 생성·갱신 요청에서는 commit이나 push 전에 아래 `검증` 절차를 적용한다.
검토한 base·HEAD와 tracked/untracked 변경 범위, 실행한 명령과 결과를 기록한다.
commit hook이나 추가 수정으로 내용이 달라지면 영향받는 검토·검증을 다시 실행한다.
검토·검증은 이 스킬 안에서 수행하며 별도 사내 도구나 외부 업무 시스템을 요구하지 않는다.

1. 현재 브랜치와 변경 범위를 확인한다.
2. 최근 커밋 30개의 제목을 읽어 저장소 언어와 접두어 스타일을 맞춘다.
  - `git log -30 --pretty=format:"%s"`
3. 변경을 독립적으로 설명하고 되돌릴 수 있는 논리 단위로 나눈다.
  - 기능 동작과 해당 테스트는 보통 같은 커밋에 둔다.
  - CLI, HID·상태 추적, 문서·도구는 실제 의존성과 관심사를 기준으로 구분한다.
  - 파일 수만으로 억지로 커밋을 쪼개지 않는다.
4. `git add <명시적 경로>` 또는 `git add -p`로 필요한 변경만 스테이징한다.
  - 전체 변경이 확실히 같은 범위가 아니면 `git add -A`를 사용하지 않는다.
5. 의존 순서대로 커밋한다.
  - 모델·설정 → 상태 추적·HID → CLI → 문서·배포 설정 순서를 우선한다.
6. 결과를 검증한다.
  - `git diff --cached --check`
  - `git log --oneline -n <개수>`
  - `git status --short --branch`
7. 푸시가 요청된 경우 현재 브랜치와 upstream을 재확인한 뒤 푸시한다.
8. PR 생성이 요청되면 아래 PR 작성 규칙을 따른다.

## 커밋 메시지

- 반드시 한국어 Conventional Commits 형식으로 작성한다: `<type>(<scope>): <한국어 요약>`.
- `scope`가 명확하지 않으면 `<type>: <한국어 요약>` 형식을 사용한다.
- `type`은 `feat`, `fix`, `refactor`, `style`, `docs`, `test`, `chore`, `perf`, `ci` 중에서 고른다.
- 제목은 50자 이내를 지향하고 끝에 마침표를 붙이지 않는다.
- 코드 식별자, API 이름, 파일명, 패키지명은 원문 그대로 둔다.

## 브랜치명

- 새 브랜치는 변경 목적을 드러내는 영어 소문자 kebab-case 이름을 권장한다.
- 기존 Orca 작업 브랜치는 이름 형식을 맞추려고 변경하지 않는다.
- `update-files`, `fix-stuff`, `changes` 같은 일반적인 이름을 피한다.

## 검증

변경 범위에 맞는 가장 작은 검증을 먼저 실행한다. 저장소의 `AGENTS.md`가 있으면 따르고,
`pyproject.toml`과 `.github/workflows/`의 현재 정의를 확인한다.

### PR 전 로컬 검증

1. base 대비 branch와 workspace diff를 검토한다. 새로 도입된 버그가 있으면 해결하고 다시 검토한다.
2. `git diff --check`와 `git diff --cached --check`를 실행한다. untracked 파일도 PR 범위에 포함되면 직접 검토한다.
3. Python 코드 변경은 개발 환경에서 `python -m pytest --junitxml=<임시-결과-경로>`와
 `python -m ruff check .`를 실행한다. 환경이 없으면 별도 가상환경에 `python -m pip install ".[dev]"`로 준비한다.
4. 스킬의 Python 도구를 변경하면 `python -m pytest .agents/skills/keychron-git/scripts/`와
 `python -m ruff check .agents/skills/keychron-git/`를 별도로 실행한다.
5. 필요한 검사 실패는 통과로 처리하지 않는다. 미실행 검사와 이유를 PR에 적고 검증 미완료 PR은 draft로 만든다.

문서만 바뀌면 제품 테스트는 생략할 수 있다. 검토·검증 후 코드가 바뀌면 관련 검사를 다시 실행한다.

### CI와 실기기 검증의 구분

- `.github/workflows/tests.yml`은 PR 이벤트로, `publish.yml`은 `main` push 또는 수동 실행으로 동작한다.
- 두 workflow는 새 wheel을 빌드하고 Python 3.9·3.13에서 `scripts/requirements.py --verify-tests`로 pytest·Bun과 요구사항 연결을 검사한다. Python 3.13에서는 Ruff도 실행한다. 로컬 단일 Python 결과를 전체 matrix 통과로 쓰지 않는다.
- 이후 태그 생성, 패키지 빌드, PyPI 게시, GitHub Release가 이어진다. PR 생성 권한을 merge나 릴리스 권한으로 해석하지 않는다.
- 패키징 변경은 필요에 따라 `python -m build`와 `python -m twine check --strict dist/*`를 검증한다.
- HID·키 입력·권한·자동 실행 변경은 단위 테스트와 실제 macOS/Keychron 확인을 구분한다.
실기기 확인 없이 LED 출력·키보드 제어가 검증됐다고 보고하지 않는다.

## PR 작성 규칙

모든 Pull Request 제목과 본문은 반드시 한국어로 작성한다.

### 작성 전 수집

```bash
git status --short --branch
git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref @{upstream} 2>/dev/null || true
git log --oneline main..HEAD
git diff --stat main...HEAD
git diff main...HEAD
python3 .agents/skills/keychron-git/scripts/pr_diff_summary.py main
python3 .agents/skills/keychron-git/scripts/pr_test_summary.py <junit-result-path>
gh pr view --json title,body,baseRefName,url 2>/dev/null || true
```

base가 `main`이 아니면 사용자 지정 base를 사용한다. 기존 PR이 있으면 현재 제목·본문도 함께 검토한다.
전체 변경 파일 수·추가 줄·삭제 줄·순증감과 현재 HEAD에서 실행한 테스트의 성공·실패·건너뜀 수도 수집한다.

### 본문 섹션 순서

- H2 섹션은 `ELI5 → Summary → 테스트 및 검증 → 상세 변경 → 리뷰 → References` 순서로 고정한다.
- `ELI5`에는 전문용어를 풀어 비개발자도 변경 목적과 결과를 이해할 수 있는 1~2문장을 인용문으로 작성한다.
- `Summary`에는 기존 핵심 요약 목록과 Diff 요약 표를 함께 둔다.
- `테스트 및 검증`에는 검증 상태판, 테스트 결과 표와 필요한 검증 Flow를 둔다.
- `상세 변경`에는 영역별 변경 표·차트와 구현 세부사항을 둔다.

### Diff 요약 표

- `python3 .agents/skills/keychron-git/scripts/pr_diff_summary.py <base>`를 저장소 루트에서 실행한다.
- 출력 표를 Summary의 핵심 요약 목록 바로 아래에 둔다.
- PR 전체 diff를 한 줄로 합산한다. 바이너리는 Files에 포함하고 줄 수는 0으로 계산한다.
- Added와 양수 Net은 `#1f883d`, Deleted와 음수 Net은 `#cf222e`, 0은 `#656d76` 색상의 굵은
GitHub inline math로 표시한다. 원형 색상 이모지는 사용하지 않는다.
- 부호는 숫자에 직접 붙여 양수는 `+`, 음수는 `−`로 표시한다.
- 기존 PR을 수정할 때는 기존 표를 새 값으로 교체한다.

### 테스트 결과 표

- 필요한 로컬 검토·검증을 통과한 경우 `테스트 및 검증` 첫 내용으로 검증 상태판을 넣고, 테스트 표를 그 바로 아래에 둔다.
- JUnit XML이 있으면 `python3 .agents/skills/keychron-git/scripts/pr_test_summary.py <result-path>`로 합산한다.
- 다른 테스트 러너는 현재 HEAD에서 실행한 출력으로 같은 형식의 값을 작성한다.
- 이전 커밋이나 다른 브랜치의 결과를 재사용하지 않는다.
- 테스트를 실행하지 않았으면 `⚪ Not run`과 `-`를 표시하고 `리뷰` 섹션에 이유를 쓴다.
- 실패가 있으면 `❌ Failed`와 실패 건수를 표시하고 PR을 draft로 만든다.
- 기존 PR을 수정할 때는 기존 테스트 표를 새 값으로 교체한다.

### 제목 규칙

- 한국어 Conventional Commits 형식으로 작성한다.
- PR 전체 변경의 최종 동작을 대표하는 `type`과 `scope`를 고른다.
- 50자 이내를 지향하고 끝에 마침표를 붙이지 않는다.
- 고유명사·기술용어·코드 식별자는 원문 그대로 둔다.

### 본문 양식

아래 숫자와 상태는 예시다. 실제 diff·검토·테스트 결과로 교체하고, 미검증 상태를 성공으로 표시하지 않는다.

```markdown
## ELI5

> 비개발자도 변경 목적과 결과를 이해할 수 있도록 1~2문장으로 쉽게 설명한다.

## Summary

- 변경 내용과 필요한 이유를 결론부터 요약한다.
- 주요 동작 변화와 영향 범위를 요약한다.

| Files | Added | Deleted | Net |
| ---: | ---: | ---: | ---: |
| **12** | $\color{#1f883d}{\mathbf{+496}}$ | $\color{#cf222e}{\mathbf{−114}}$ | $\color{#1f883d}{\mathbf{+382}}$ |

## 테스트 및 검증

> [!IMPORTANT]
> ### 🟢 READY FOR REVIEW
> **필요한 로컬 검토·검증 통과** · Finding **0건** · 테스트 실패 **0건**

| Test Status | Passed | Failed | Skipped |
| :--- | ---: | ---: | ---: |
| ✅ Success | 21 | 0 | 0 |

## 🔎 상세 변경

## 💬 리뷰

## 📎 References
```

### 본문 작성 원칙

1. `ELI5`로 쉬운 결론을 먼저 보여주고 Summary에서 기술적 근거·맥락을 잇는다.
2. Summary에는 변경 내용, 필요한 이유, 검증 결과를 짧게 담는다.
3. 코드 diff의 단순 나열보다 동작 변화와 설계 의도를 설명한다.
4. 영향받는 모듈, API, 데이터 흐름을 실제 변경 기준으로 구체화한다.
5. 리뷰에는 트레이드오프, 잠재 리스크, 확인할 엣지 케이스를 쓴다.
6. 실행한 테스트와 결과를 남기고 미검증 영역을 숨기지 않는다.
7. References에는 실제로 참조한 문서만 연결하고, 없으면 `- 없음`으로 명시한다.
8. 변경 구조, 데이터 흐름, 컴포넌트 관계 또는 처리 순서가 복잡하면 Mermaid로 시각화한다.
9. 검증 Flow는 `테스트 및 검증`, 변경 구조 시각화는 `상세 변경` 또는 `리뷰`에서 관련 설명을 보완한다.
10. Mermaid에는 수집한 커밋·diff에서 확인 가능한 실제 변경만 넣고 추측 구성은 넣지 않는다.
11. 단순 변경이거나 리뷰 이해에 실질적으로 도움이 안 되면 Mermaid를 생략한다.
12. GitHub에서 렌더링 가능한 `mermaid` 코드 블록을 사용한다.
13. 노드명과 연결 설명은 간결하게 작성한다.
14. 다이어그램만으로 본문 설명을 대체하지 않는다.
15. 기존 PR의 Mermaid가 현재 patch와 다르면 수정하거나 제거한다.

### PR 생성·수정

1. 대상 base, 현재 브랜치, 원격 브랜치, 기존 PR을 확인한다.
2. PR에 포함될 커밋과 전체 patch를 검토한다.
3. 관련 lint·테스트를 실행한다.
4. 원격 브랜치가 없거나 뒤처져 있으면 사용자 요청 범위에서 푸시한다.
5. 정해진 H2 섹션 순서로 본문을 작성하고 `gh pr create` 또는 `gh pr edit`로 반영한다.
   CLI로 여러 줄 본문을 전달할 때는 임시 Markdown 파일과 `--body-file`을 사용한다. 검증이 완료되지 않았으면
 `READY FOR REVIEW` 상태판을 표시하지 않는다.
6. 검증이 미완료이거나 사용자가 요청하면 draft로 만든다.
7. 생성·수정 후 PR URL을 보고한다.

제목·본문만 요청된 경우에는 Git 상태를 바꾸지 않고 작성 결과만 반환한다.

## Merge commit 메시지

- PR 생성과 merge는 별도 권한이다. PR 생성만 요청받았다면 merge하지 않는다.
- PR 생성·수정 시 merge 화면에 넣을 `Commit message`와 `Extended description`도 함께 작성해 결과 보고에 포함한다.
- `Commit message`는 PR 제목을 그대로 사용한다. `Merge pull request #...` 같은 GitHub 기본 문구를 권장값으로 사용하지 않는다.
- `Extended description`은 PR 본문을 그대로 복사하지 않고 다음 형식의 한국어 2~5줄로 요약한다.
  - 첫 줄: 최종 동작과 필요한 이유
  - 다음 줄: 핵심 구현 1~3개
  - 마지막 줄: 검증 결과 또는 의도적으로 미실행한 검증
- 표, Mermaid, 체크리스트, PR 번호, 리뷰 지침은 Extended description에서 제외한다.
- merge 전 저장소 기본 설정을 확인한다. `gh pr create`와 `gh pr edit`는 merge 화면 입력값을 직접 지정할 수 없으므로,
웹 UI 기본값이 권장값과 다르면 현재 설정과 복사할 정확한 두 값을 함께 보고한다.

```bash
repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
gh api "repos/${repo}" --jq '{merge_commit_title,merge_commit_message,squash_merge_commit_title,squash_merge_commit_message}'
```

- 사용자가 merge까지 요청하면 방식과 두 메시지를 명시하고 아래처럼 적용한다.

```bash
title="$(gh pr view <pr> --json title --jq .title)"
gh pr merge <pr> --merge --subject "$title" --body "$extended_description"
# squash가 요청된 경우 --merge 대신 --squash를 사용한다.
```

- 웹 merge 화면의 자동 기본값을 바꾸려면 저장소 전체 설정 변경이 필요하다. 모든 PR에 영향을 주므로 사용자가 명시적으로
승인한 경우에만 `merge_commit_title=PR_TITLE`, `merge_commit_message=PR_BODY` 같은 설정을 적용한다.
- merge 후 실제 생성된 커밋 메시지를 검증한다.
- 저장소 전체 merge 설정은 사용자가 명시적으로 요청한 경우에만 변경한다.

## 히스토리 변경 안전 규칙

- 리베이스나 커밋 재작성 전 대상 브랜치, upstream, 이미 푸시된 커밋 여부를 확인한다.
- 공유 브랜치 또는 다른 사람의 커밋을 재작성할 가능성이 있으면 실행 전에 위험을 알린다.
- 충돌 해결 시 사용자 변경을 추측해서 버리지 않는다.
- 체리픽은 대상 SHA와 적용 브랜치를 먼저 명시하고 적용 후 중복 변경과 테스트 상태를 확인한다.
- 삭제, reset, checkout을 통한 변경 폐기는 명시적인 승인 없이 수행하지 않는다.

## 결과 보고

Git 작업을 실제 수행한 경우 다음을 간단히 보고한다.

```text
감지한 커밋 스타일: ...
생성/변경한 커밋:
1. <sha> <message> - <범위>
검증: <실행한 명령과 결과>
남은 변경: <없음 또는 제외한 파일>
푸시 상태: <미실행 또는 원격 브랜치>
PR: <URL 또는 미실행>
Merge Commit message: <PR 제목>
Merge Extended description: <최종 동작·구현·검증 요약>
```
