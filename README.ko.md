<p align="center">
  <a href="#gjc-keychron"><img src="assets/img3.png" alt="가재코드 Keychron: 가재 캐릭터와 상태 표시 키보드" width="44%"></a>
  <a href="#basic-keychron"><img src="assets/img4.png" alt="기본 Keychron: Orca 캐릭터와 상태 표시 키보드" width="44%"></a>
</p>

<div align="center">

# Orca Keychron

### 작업 상태는 키 색으로, 필요한 터미널은 단축키로.

**기본 Keychron · 가재코드 Keychron — 사용하는 작업 방식에 맞게 선택하세요.**

![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![플랫폼: macOS](https://img.shields.io/badge/platform-macOS-000000?logo=apple&logoColor=white)
![라이선스: MIT](https://img.shields.io/badge/license-MIT-2ea44f)

[English](README.md) · **한국어**

</div>

Orca에서 여러 작업을 실행해 놓고 모든 터미널을 계속 지켜볼 필요는 없습니다.
Keychron의 숫자 키 색으로 상태를 확인하고, `Option + 표시 키`를 눌러 필요한 터미널로 이동하세요.

## 어떤 버전을 선택하면 되나요?

**하나의 `orca-keychron` 패키지에 두 모드가 들어 있습니다.** 두 모드는 v0.1.3부터 함께 제공하며,
이 문서에서 말하는 “버전”은 사용 모드를 뜻합니다. 키보드 한 대에는 한 번에 한 모드만 실행합니다.

| 선택 기준 | 기본 Keychron — Orca 모드 | 가재코드 Keychron — GJC 모드 |
|---|---|---|
| 이런 분께 | Orca가 관리하는 여러 에이전트·워크트리를 보고 싶을 때 | Orca 터미널에서 실행한 가재코드와 자식 에이전트를 보고 싶을 때 |
| 키 하나의 기준 | 워크트리 하나 | 대화형 `gjc` 실행 하나 |
| 상태를 받는 방법 | Orca CLI를 주기적으로 조회 | GJC 네이티브 훅이 변경 상태를 전달 |
| `Option + 표시 키` | 워크트리의 확인할 에이전트로 이동·순환 | 해당 GJC를 실행한 부모 터미널로 이동 |
| 실행 명령 | `orca-keychron` | `orca-keychron-gjc` |

[기본 Keychron 시작](#basic-keychron) · [가재코드 Keychron 시작](#gjc-keychron) ·
[모드 전환](#switch-modes) · [문제 해결](#troubleshooting) · [개발·검증](#development)

## 공통 준비와 설치

- Python 3.9 이상이 설치된 macOS와 [uv](https://docs.astral.sh/uv/).
- 실행 중인 Orca와 `PATH`에서 사용할 수 있는 `orca` CLI.
- USB로 연결한 호환 Keychron 키보드. Bluetooth는 필요한 raw HID 인터페이스를 보통 제공하지 않습니다.
- 키별 `KC_RGB` 명령 `0xA8`을 지원하는 펌웨어. **Keychron Q65 Max**에서 확인했으며 `setup`이 지원 여부를 검사합니다.

```bash
uv tool install 'orca-keychron>=0.1.3'
```

이미 설치했다면 `uv tool upgrade orca-keychron`으로 업그레이드합니다.
**패키지 버전과 GJC 버전은 다릅니다.** 가재코드 모드는 별도로 **GJC 0.16.4**가 필요합니다.

<p align="center">
  <img src="https://raw.githubusercontent.com/KMGeon/orca-keychron/main/assets/img2.png" alt="Keychron Q65 Max의 상태 표시 키" width="720">
</p>

<a id="basic-keychron"></a>
## 1. 기본 Keychron — Orca 모드

**워크트리별로 여러 코딩 에이전트를 관리할 때 사용합니다.** Codex, Claude Code, Grok 등
Orca가 상태를 제공하는 에이전트가 대상이며, 로컬과 페어링된 호스트를 기본적으로 포함합니다.
에이전트마다 별도 훅을 설치할 필요가 없습니다.

![기본 Orca 모드의 워크트리 상태 표시와 터미널 이동](https://raw.githubusercontent.com/KMGeon/orca-keychron/main/assets/img1.png)

### 시작하기

다른 모드가 실행 중이면 먼저 [모드 전환](#switch-modes)을 따르세요.

```bash
orca-keychron setup
```

`setup`이 Orca 연결·키보드 지원을 확인하고 표시 영역을 미리 보여줍니다.
설정과 macOS 권한을 준비한 뒤 **로그인 시 자동 시작하는 서비스까지 설치·실행**합니다.
기본 표시 영역은 `1 2 3 4 5 6 7 8 9 0 - =`입니다.
Orca에서 에이전트 작업을 시작하면 배정된 키에 상태가 표시됩니다. Orca를 앞에 두고 `Option + 표시 키`로 이동해 보세요.

```bash
orca-keychron status
orca-keychron autostart status
```

자동 시작 없이 직접 실행하려면 위의 `setup` 대신 다음 명령을 사용합니다.

```bash
orca-keychron setup --no-autostart
orca-keychron run
```

일회성으로 사용할 때는 같은 명령을 `uvx orca-keychron setup --no-autostart`,
`uvx orca-keychron run`으로 실행할 수도 있습니다.

### 색상과 이동

| 색상 | 의미 |
|---|---|
| 🟡 노란색 | 작업 중 |
| 🟠 주황색 | 답변·승인 대기 |
| 🔴 빨간색 | 차단·실패 상태 확인 필요 |
| 🟢 초록색 | Orca가 보고한 완료 상태 |
| 🟣 자홍색 | 대기·차단·완료 중 여러 종류가 함께 있어 확인 필요 |
| 🩵 하늘색 | 활성 에이전트가 없는 유지 슬롯 또는 미배정 키 |

작업 중인 에이전트가 있다는 이유만으로 자홍색이 되지는 않습니다.
여러 확인 대상이 있으면 `Option + 같은 표시 키`를 놓았다가 다시 눌러
**차단 → 대기 → 완료** 순서로 이동합니다. 오래된 완료 기록은 같은 터미널 패널의 활동을 먼저 관찰하기 전까지 무시합니다.

<a id="gjc-keychron"></a>
## 2. 가재코드 Keychron — GJC 모드

**Orca 안에서 실행한 [가재코드](https://github.com/Yeachan-Heo/gajae-code)의 상태를 보고 싶을 때 사용합니다.**
GJC 소스를 수정하거나 별도 실행기로 감쌀 필요 없이, 훅을 설치한 뒤 평소처럼 `gjc`를 실행합니다.
**현재 컴퓨터의 Orca 터미널이 대상**이며, 기본 모드처럼 페어링된 원격 호스트의 실행을 모으지는 않습니다.

### 한눈에 보는 동작

[![GJC 실행별 키 배정, 네이티브 훅의 로컬 상태 전달, 색상 우선순위와 부모 터미널 이동](assets/img5.png)](assets/img5.png)

*그림을 누르면 크게 볼 수 있습니다. 키에 표시된 색은 상태 예시이며, 특정 번호에 고정된 색이 아닙니다.*

1. **키 배정:** 대화형 `gjc` 실행 하나에 키 하나를 배정합니다. 자식 에이전트는 부모의 키를 공유합니다.
2. **색상 표시:** 훅이 관찰한 상태를 로컬 수신기로 전달하면, 확인이 필요한 상태의 우선순위에 따라 키 색이 바뀝니다.
3. **터미널 이동:** Orca를 앞에 두고 `Option + 표시 키`를 누르면 해당 GJC를 실행한 부모 터미널로 이동합니다.

### 실제 사용 예시

슬롯이 비어 있는 상태라면 다음처럼 배정됩니다.

```text
터미널 A에서 gjc 실행 → 1번 키
터미널 B에서 gjc 실행 → 2번 키
A 안에서 자식 에이전트 10개 생성 → 모두 1번 키에 상태를 모아 표시
```

**A에서 10명이 작업 중이어도 1명의 답변 대기가 관찰되면 1번 키는 주황색입니다.**
색은 다수결로 정하지 않습니다. B의 상태는 별도로 2번 키에 표시합니다.
`Option + 1`은 A의 부모 터미널로 이동합니다. 개별 자식 목록을 펼치거나 자식 답변창을 직접 여는 동작은 제공하지 않습니다.

### 시작하기

다른 모드가 실행 중이면 먼저 [모드 전환](#switch-modes)을 따르세요.

1. `gjc --version`이 **`gjc/0.16.4`**인지 확인합니다.
2. 키보드를 설정하고 GJC 훅을 설치합니다.

   ```bash
   orca-keychron-gjc setup
   orca-keychron-gjc install --dry-run
   orca-keychron-gjc install
   ```

3. 상태 표시 프로그램을 실행합니다. 이 터미널은 실행 상태로 둡니다.

   ```bash
   orca-keychron-gjc run
   ```

4. **다른 Orca 터미널**에서 `gjc`를 실행합니다. 이미 열려 있던 GJC는 작업을 정리하고 다시 시작해야 새 훅을 읽습니다.
5. 다른 터미널에서 연결 상태를 확인합니다.

   ```bash
   orca-keychron-gjc doctor
   orca-keychron-gjc status
   ```

GJC의 `setup`은 설정만 준비합니다. 로그인 시 자동 시작하려면 포그라운드 `run`을
`Ctrl-C`로 종료한 다음 아래 명령을 실행합니다.

```bash
orca-keychron-gjc autostart install
orca-keychron-gjc autostart status
```

### 색상 읽는 법

| 색상 | 의미 |
|---|---|
| 🟠 주황색 | 관찰된 미해결 질문·의사결정 요청 |
| 🔴 빨간색 | 관찰된 턴·워커 실패 |
| 🟡 노란색 | 작업 중 |
| ⚪ 흰색 | 연결 단절·상태 불확실 |
| 🟢 초록색 | 현재 턴 응답 종료. 전체 목표 완성을 뜻하지 않음 |
| 🩵 하늘색 | 입력 대기 또는 미배정 키 |

연결된 실행의 우선순위는 **대기 → 실패 → 작업 중 → 불확실 → 턴 종료 → 입력 대기**입니다.
연결이 끊기면 이전 색 대신 흰색을 표시하고 슬롯은 유지합니다. 상태 전달은 변경 이벤트 중심이며,
2초 간격의 연결 확인 신호와 8초 연결 유효기간으로 연결 상태도 확인합니다.

### 재시작과 남은 키 정리

같은 GJC 프로세스 안의 자식과 `/new`는 키를 공유합니다. 수신기 재시작·재연결은 기존 배정을
복원할 수 있지만, **GJC 프로세스를 새로 실행하면 새 실행으로 취급**합니다. 키가 꽉 차면 추가 실행은 빈자리를 기다립니다.

정상 종료하면 슬롯이 반환됩니다. 비정상 종료 후 흰색 슬롯이 남았다면, 수신기를 실행한 상태에서
`orca-keychron-gjc status`로 실행 ID를 확인하고 `orca-keychron-gjc clear <launch_id>`로 정리합니다.
**연결이 끊겼고 프로세스 종료가 확인된 실행만** 정리할 수 있습니다. 실행 중이거나 종료 여부가 불확실하면 슬롯을 보존합니다.

### 질문 전달과 지원 범위

모든 종류의 승인창을 감지하지는 않습니다. 자식 질문을 부모에게 전달하는 흐름에는
설치 시 함께 배치되는 `keychron-decision-worker`를 선택해 사용합니다. 설치만으로 모든 자식 질문이 자동 전달되지는 않습니다. [GJC 사용자 가이드](docs/gjc-guide.md)에서 지원 범위와 질문 전달 방식을 확인하세요.

<a id="switch-modes"></a>
## 모드 전환·업그레이드·제거

**두 모드를 동시에 실행하지 마세요.** 먼저 실행 중인 `run`을 `Ctrl-C`로 종료하고,
기존 모드의 서비스를 해제한 뒤 원하는 모드의 시작 절차를 따릅니다.

| 전환 | 먼저 실행 | 다음 행동 |
|---|---|---|
| 기본 → GJC | `orca-keychron autostart uninstall` | GJC의 setup·훅 설치·실행 절차 |
| GJC → 기본 | `orca-keychron-gjc autostart uninstall` | 기본 모드의 `orca-keychron setup` |

설정·훅 설치가 끝난 모드라면 해당 모드의 `autostart install`로 자동 시작을 켤 수 있습니다.
공유 잠금은 두 표시 프로그램의 동시 제어를 막지만, Keychron Launcher 같은 다른 프로그램까지 차단하지는 않습니다.

패키지 업그레이드는 `uv tool upgrade orca-keychron`입니다. GJC 사용자는 업그레이드 후
`orca-keychron-gjc install`을 다시 실행하고 GJC도 다시 시작해 새 훅을 적용합니다.

완전히 제거할 때는 실행 중인 `run`을 종료하고, 사용하는 모드의 `autostart uninstall`을 실행합니다.
GJC 훅을 설치했다면 `orca-keychron-gjc uninstall`도 실행한 뒤 `uv tool uninstall orca-keychron`으로 패키지를 제거합니다.
저장된 설정·로그는 자동 삭제하지 않습니다.

## 공통 설정과 macOS 권한

두 모드 모두 Orca가 앞에 있을 때 `Option + 표시 키`로 이동합니다. 키를 길게 누를 필요는 없으며,
일반 숫자 입력·다른 앱의 단축키·`Shift`·`Control`·`Command`를 함께 누른 입력은 가로채지 않습니다.

**시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 / 입력 모니터링**에서
표시 프로그램을 실행하는 Python 또는 터미널을 허용하세요. 권한 변경 뒤 사용하는 모드의 프로그램을 재시작합니다.

| 설정 | 기본 Keychron | 가재코드 Keychron |
|---|---|---|
| 설정 파일 | `~/Library/Application Support/orca-keychron/config.json` | `~/Library/Application Support/orca-keychron/gjc/config.json` |
| 표시 위치 변경 | `orca-keychron setup --leds 1,2,3` | `orca-keychron-gjc setup --leds 1,2,3` |
| 자세한 옵션 | `orca-keychron run --help` | `orca-keychron-gjc run --help` |

LED 번호는 키에 적힌 숫자가 아닌 펌웨어 내부 위치입니다. `setup`의 미리보기로 위치를 확인하세요.
GJC 소켓을 별도로 지정한다면 `orca-keychron-gjc setup --socket /absolute/path/bridge.sock`을 먼저 실행하고 훅을 설치합니다.
소켓 설정을 바꾼 뒤에는 훅도 다시 설치해야 합니다.

<a id="troubleshooting"></a>
## 문제 해결과 지원 범위

| 증상 | 먼저 확인할 것 |
|---|---|
| 불이 안 들어옴 | USB 연결·`KC_RGB` 지원·선택한 모드의 `run` 오류. 기본은 `status`, GJC는 `doctor`와 `status`로 확인 |
| 장치를 다른 프로그램이 사용 중 | 다른 모드의 서비스·포그라운드 `run`·Keychron Launcher 조명 제어 종료 |
| 단축키가 반응하지 않음 | Orca가 앞에 있는지, 손쉬운 사용·입력 모니터링 권한이 있는지 확인 |
| GJC 키가 흰색 | GJC 재시작 여부와 훅·수신기 연결 확인. 흰색만으로 실행을 삭제하지 않음 |
| 종료 후 기존 조명이 다름 | 이전 효과·밝기는 복원하지만 읽어올 수 없는 RAM 전용 커스텀 프레임은 직접 재적용 |

RGB는 RAM에 기록하며 `SaveLedConf`를 사용하지 않습니다. 이 프로젝트 자체의 외부 수집 서비스로
상태를 보내지 않습니다. 기본 모드는 Orca CLI, GJC 모드는 로컬 소켓을 사용합니다.

GJC 연동은 실제 0.16.4와 로컬 응답 대역으로 검증했습니다. Q65 Max의 RGB 프레임 응답·조명 복원과
별도 Orca pane 이동도 확인했습니다. **육안 색상 확인, 실제 Option 키 입력, 실제 모델의 질문 전달 준수**는
별도 검증 범위입니다. [하드웨어 기록](docs/gjc-hardware-validation.md)과 [전체 검증 기록](docs/testing/gjc-second-audit.md)을 참고하세요.

<a id="development"></a>
## 개발·검증·문서

구현과 테스트를 바꿀 때는 [제품 문서](docs/product/README.md)의 요구사항 ID와 함께 관리합니다.
[테스트 연결표](docs/product/test-map.md)에는 정확한 테스트와 검증 한계가 정리되어 있습니다.

저장소를 clone한 뒤 Python 3.9 이상과 Bun 1.4.0(CI 기준)을 준비하고 실행합니다.

```bash
uv venv .venv
uv pip install --python .venv/bin/python '.[dev]' build
.venv/bin/python -m build --wheel --outdir dist/test-wheel
GJC_TEST_WHEEL_DIR=dist/test-wheel .venv/bin/python scripts/requirements.py --verify-tests
.venv/bin/python -m ruff check .
```

wheel 출력 경로는 이전 산출물이 없는 새 경로를 사용하세요. 검사는 새 pytest·Bun 결과와 요구사항 연결을
확인하며, 실제 GJC 시나리오·모델·물리 키보드 검증은 별도입니다. 문서 갱신 방법은 [변경 절차](docs/product/maintenance.md)를 따릅니다.

PR에서는 Python 3.9·3.13 검사를 실행합니다. `main` 반영 후 검증이 통과하면 자동 patch 태그,
PyPI 게시와 GitHub Release가 이어집니다. [릴리스 목록](https://github.com/KMGeon/orca-keychron/releases)에서 배포본을 확인할 수 있습니다.

버그 제보에는 키보드 모델·USB 연결 방식·macOS 버전과 `orca-keychron probe` 결과를 포함해 주세요.
개인 대화·실행환경·로컬 경로·설정 파일은 공개하지 마세요.

## 라이선스

[MIT License](LICENSE)
