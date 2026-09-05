<div align="center">

# Orca Keychron

### 모든 터미널을 지켜보지 않고 Orca 에이전트를 10배 더 효율적으로 운영하세요.

Keychron 키보드를 모든 Orca 워크트리의 실시간 명령 센터로 바꿔보세요.

![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![플랫폼: macOS](https://img.shields.io/badge/platform-macOS-000000?logo=apple&logoColor=white)
![라이선스: MIT](https://img.shields.io/badge/license-MIT-2ea44f)

[English](https://github.com/KMGeon/orca-keychron/blob/main/README.md) · **한국어**

</div>

![Keychron 키보드에 표시되는 Orca 에이전트 상태](https://raw.githubusercontent.com/KMGeon/orca-keychron/main/assets/img1.png)

`orca-keychron`은 각 Orca 워크트리를 고정된 키에 할당하고 에이전트 상태를 키별
RGB로 표시합니다. 어떤 에이전트가 작업 중인지, 입력을 기다리는지, 막혔는지 또는
완료됐는지 확인하고 단축키 한 번으로 바로 해당 워크트리로 이동할 수 있습니다.

Codex, Claude Code, Grok, 로컬 세션, 페어링된 호스트의 에이전트 등 Orca가 표시하는
모든 코딩 에이전트가 자동으로 연동됩니다. 에이전트별 훅은 별도로 설치하지 않습니다.

> [!IMPORTANT]
> 이 프로젝트를 사용하려면 Keychron 키보드 펌웨어가 키별 `KC_RGB` 명령 `0xA8`을
> 지원해야 합니다. **Keychron Q65 Max**에서 검증했습니다. 다른 모델은 영구 서비스를
> 설치하기 전에 setup 명령이 자동으로 감지하고 지원 여부를 확인합니다.

<p align="center">
  <img src="https://raw.githubusercontent.com/KMGeon/orca-keychron/main/assets/img2.png" alt="Keychron Q65 Max에 표시되는 Orca 워크트리 상태 조명" width="720">
</p>

## 주요 기능

- 활성 Orca 워크트리마다 고정된 상태 표시 키를 하나씩 할당합니다.
- 같은 워크트리의 여러 에이전트 상태를 행동 중심의 단일 상태로 집계합니다.
- `Option`과 상태 표시 키를 눌러 해당 워크트리의 현재 작업 대상으로 이동합니다.
- 기본적으로 로컬 호스트와 페어링된 Orca 호스트의 에이전트를 모두 포함합니다.
- Keychron 기본 펌웨어를 사용하며 RGB 프레임을 RAM에만 기록합니다.

## 상태 색상

| Orca 워크트리 상태 | 표시 색상 | 의미 |
|---|---|---|
| **작업 중(Working)** | 🟡 노란색 | 에이전트가 작업하고 있습니다 |
| **대기 중(Waiting)** | 🟠 주황색 | 답변이나 승인이 필요합니다 |
| **차단됨(Blocked)** | 🔴 빨간색 | 현재 작업이 실패했거나 복구가 필요합니다 |
| **완료(Done)** | 🟢 초록색 | 다음 작업을 받을 준비가 됐습니다 |
| **혼합(Mixed)** | 🟣 자홍색 | 여러 종류의 상태를 확인해야 합니다 |
| **유휴 / 미배정** | 🩵 하늘색 | 해당 자리에 활성 에이전트가 없습니다 |

`working`은 백그라운드 활동으로 취급하므로 그 자체로 혼합 상태를 만들지 않습니다.
같은 pane이 실제 실행 상태로 한 번 이상 관찰되기 전까지 과거의 `done` 행은 무시하여
오래된 세션이 상태 표시 영역을 차지하지 않도록 합니다.

## 빠른 시작

### 요구 사항

- Python 3.9 이상이 설치된 macOS
- [uv](https://docs.astral.sh/uv/) 설치
- Orca가 실행 중이며 `orca` CLI를 `PATH`에서 사용할 수 있는 환경
- USB로 연결된 호환 Keychron 키보드

대부분의 Keychron 키보드는 Bluetooth 연결에서 필요한 raw HID 인터페이스를 제공하지
않습니다.

### 설치

```bash
uv tool install orca-keychron
orca-keychron setup
```

대화형 setup은 다음 작업을 수행합니다.

1. Orca 연결을 확인합니다.
2. 키보드를 감지하고 `KC_RGB` 지원 여부를 확인합니다.
3. 기본 상태 표시 영역을 미리 보여준 뒤 기존 조명으로 복원합니다.
4. 키보드 설정을 저장하고 필요한 macOS 권한을 요청합니다.
5. 사용자별 로그인 서비스를 설치하고 상태 표시기를 시작합니다.

setup이 끝나면 로그인할 때 상태 표시기가 자동으로 시작됩니다. 기본 영역은 숫자 행
`1 2 3 4 5 6 7 8 9 0 - =`입니다.

### 확인

```bash
orca-keychron status
orca-keychron autostart status
```

`status`는 키보드 조명을 변경하지 않고 Orca 상태만 읽습니다. 백그라운드 설치가
정상이면 `Login autostart installed and loaded`가 출력됩니다.

### 일회성 실행

패키지를 계속 설치해 두거나 자동 시작을 등록하지 않고 실행할 수 있습니다.

```bash
uvx orca-keychron setup --no-autostart
uvx orca-keychron run
```

### 업그레이드 또는 제거

```bash
# 업그레이드
uv tool upgrade orca-keychron

# 서비스와 명령 제거
orca-keychron autostart uninstall
uv tool uninstall orca-keychron
```

제거 과정에서 사용자 데이터를 예기치 않게 삭제하지 않도록 저장된 설정과 로그는
`~/Library/Application Support/orca-keychron/`에 남겨둡니다. 더 이상 필요하지 않은
경우에만 해당 디렉터리를 별도로 삭제하세요.

## 키보드 탐색

Orca가 가장 앞에 있을 때 `Option`과 켜져 있는 상태 표시 키를 함께 누르면 해당
워크트리의 현재 작업 대상이 열립니다. 같은 워크트리에 확인이 필요한 에이전트가
여러 개 있으면 키를 반복해서 눌러 다음 순서로 이동할 수 있습니다.

```text
blocked → waiting → done
```

일반 숫자 키와 `Control`, `Command` 또는 여러 modifier를 조합한 단축키는 가로채지
않습니다. 다른 애플리케이션이 가장 앞에 있을 때의 Option-숫자 단축키도 그대로
전달됩니다. Orca가 가장 앞에 있을 때 할당되지 않은 표시 키를 누르면 아무 동작도
하지 않습니다.

## 동작 방식

```text
Orca가 관리하는 에이전트
        │ 정규화된 생명주기 상태
        ▼
orca worktree ps --json
        │ 0.75초마다 조회
        ▼
고정된 워크트리 슬롯 추적기
        │ 워크트리별 에이전트 집계
        ▼
상태 렌더러 + 작업 대상 추적기
        │ KC_RGB raw HID, RAM 전용
        ▼
Keychron 키별 RGB
```

Orca는 에이전트 활동을 이미 `working`, `waiting`, `blocked`, `done`으로 정규화합니다.
이 프로젝트는 Codex, Claude Code 또는 Grok 생명주기 훅을 다시 설치하지 않고 Orca가
공개하는 상태 정보를 사용합니다.

하나의 장기 실행 프로세스가 별도 작업 스레드에서 Orca 상태를 조회하고 키보드 HID 핸들을 소유합니다.
렌더링된 상태가 바뀔 때만 RGB를 갱신하며 10초마다 선택한 조명 효과를 확인합니다.

## 설정

setup은 다음 위치에 설정을 저장합니다.

```text
~/Library/Application Support/orca-keychron/config.json
```

setup에서 다른 상태 표시 영역을 선택할 수 있습니다.

```bash
orca-keychron setup --leds 1,2,3,4,5,6,7,8,9,10
```

LED 인덱스는 키에 인쇄된 문자가 아니라 펌웨어 내부 위치이므로 키보드마다 다를 수
있습니다. setup은 선택한 인덱스를 저장하기 전에 키보드에서 미리 보여줍니다.

자주 사용하는 실행 옵션은 다음과 같습니다.

| 옵션 | 용도 |
|---|---|
| `--open-hold 0.3` | 워크트리를 열기 전에 짧게 누르고 있도록 설정합니다 |
| `--poll-interval 0.75` | Orca 상태 조회 주기를 변경합니다 |
| `--leds 1,2,3` | 저장된 상태 표시 LED 인덱스를 덮어씁니다 |
| `--host local` | 특정 호스트만 포함합니다. 여러 호스트를 포함하려면 반복합니다 |
| `--orca-command orca-dev` | 다른 Orca CLI 명령을 사용합니다 |

전체 명령 안내는 `orca-keychron <command> --help`로 확인할 수 있습니다.

## macOS 권한

키보드 탐색 기능에는 **손쉬운 사용**과 **입력 모니터링** 권한이 모두 필요합니다.
다음 설정에서 설치된 Python 프로세스 또는 상태 표시기를 실행하는 터미널을
허용하세요.

```text
시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용
시스템 설정 → 개인정보 보호 및 보안 → 입력 모니터링
```

그런 다음 백그라운드 서비스를 다시 시작합니다.

```bash
orca-keychron autostart install
```

서명되지 않은 Python 도구는 macOS 권한 식별자가 안정적이지 않습니다. macOS에서
권한이 계속 필요하다고 표시되면 오래된 항목을 제거하고 현재 설치된 Python 프로세스
또는 터미널을 다시 추가한 뒤 서비스를 재설치하세요. 이 플랫폼 제약을 완전히
제거하려면 프로젝트를 서명된 macOS 애플리케이션으로 패키징해야 합니다.

## 프로토콜과 안전성

- Keychron VID `0x3434`, usage page `0xFF60`, usage `0x61`을 탐색합니다.
- VIA 채널 3과 키별 효과 `23`을 사용합니다.
- 전체 RGB 프레임을 키보드 RAM에만 전송하며 `SaveLedConf`는 사용하지 않습니다.
- 상태 표시기가 실행되는 동안 표시 영역 밖의 LED는 끕니다.
- 프로세스가 정상적으로 종료되면 기존 효과와 밝기를 복원합니다.

지원하는 프로토콜에서는 기존 키별 효과 또는 혼합 효과의 RAM 전용 프레임 내용을
다시 읽을 수 없습니다. 상태 표시기를 실행하기 전에 이러한 조명을 사용했다면 종료한
후 해당 조명 프로필을 다시 적용하세요.

이 프로젝트는 텔레메트리를 수집하거나 자체 네트워크 서비스로 에이전트 상태를
전송하지 않습니다. 설정된 Orca CLI를 호출하고 로컬 설정 및 서비스 로그만 기록합니다.

Keychron Launcher도 같은 raw HID 채널을 사용합니다. 두 애플리케이션 중 하나가
응답하지 않거나 색상을 덮어쓰면 장시간 실행 중인 Launcher 조명 애니메이션을
종료하세요.

## 문제 해결

### 불이 들어오지 않는 경우

```bash
orca-keychron status
orca-keychron autostart status
orca-keychron run
```

포그라운드에서 실행하면 오류가 즉시 출력됩니다. 백그라운드 로그는 다음 위치에
저장됩니다.

```text
~/Library/Application Support/orca-keychron/logs/stdout.log
~/Library/Application Support/orca-keychron/logs/stderr.log
```

### Keychron raw HID 인터페이스를 찾지 못하는 경우

Bluetooth 대신 USB로 키보드를 직접 연결하세요. Keychron Launcher를 종료한 뒤 다시
시도하세요. 일부 독과 KVM은 필요한 HID 인터페이스를 안정적으로 전달하지 못합니다.

### 펌웨어에서 `KC_RGB`를 지원하지 않는 경우

연결된 펌웨어가 명령 `0xA8`로 개별 LED를 제어할 수 없는 상태입니다. 일반 VIA 조명
지원만으로는 충분하지 않습니다. 워크트리별 표시가 사라지는 것을 막기 위해 전체
키보드 효과로 대체하지 않습니다.

### Option 키 탐색이 동작하지 않는 경우

상태 표시기를 실행하는 Python 프로세스 또는 터미널에 손쉬운 사용과 입력 모니터링
권한이 있는지 확인한 뒤 다음 명령으로 다시 시작하세요.

```bash
orca-keychron autostart install
```

### 조명이 초기화되거나 응답하지 않는 경우

Keychron Launcher 애니메이션을 종료하고 키보드를 USB로 다시 연결한 뒤 상태 표시기를
재시작하세요. 한 번에 하나의 프로세스만 raw HID 조명 채널을 제어해야 합니다.

## 개발

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

## 릴리즈

병합된 pull request를 포함해 `main`에 push가 발생할 때마다 전체 테스트와 lint를
실행합니다. 모두 통과하면 GitHub Actions가 patch 버전을 자동으로 올리고,
`github-actions[bot]` 명의의 `vX.Y.Z` annotated tag를 생성한 다음 Trusted Publishing으로
PyPI에 배포하고 동일한 산출물을 첨부한 GitHub Release를 생성합니다. 실패한 작업은 새
버전을 만들지 않고 다시 실행할 수 있습니다.

프로젝트 구조는 다음과 같습니다.

```text
src/orca_keychron/   CLI, Orca 연동, 탐색, 추적, HID 렌더링
tests/               단위 테스트와 동작 테스트
assets/img1.png      이 README에서 사용하는 아키텍처 및 상호작용 이미지
assets/img2.png      이 README에서 사용하는 Keychron Q65 Max 실물 사진
```

## 기여하기

버그 제보, 호환성 결과, 문서 개선, 범위가 명확한 pull request를 환영합니다. 저장소를
fork하고 clone한 뒤 별도 브랜치를 만들고 위의 개발 명령을 사용하세요. 하드웨어 관련
제보에는 Keychron 모델, 연결 방식, macOS 버전과 다음 읽기 전용 probe 결과를
포함해 주세요.

```bash
orca-keychron probe
```

Pull request를 열기 전에 다음 명령을 실행하세요.

```bash
.venv/bin/pytest
.venv/bin/ruff check .
```

Issue에는 개인 Orca 상태, 로컬 경로 또는 설정 파일을 포함하지 마세요.

## 라이선스

[MIT License](https://github.com/KMGeon/orca-keychron/blob/main/LICENSE)에 따라 배포됩니다.
