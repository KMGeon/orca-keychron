# Orca Keychron의 GJC 패키지 구조

상태: 현재 source/package 경계를 기록한다. 이 문서는 설치, 배포, 물리 하드웨어 또는 실제 모델 E2E 완료를 주장하지 않는다.

## 배포와 실행 명령

저장소는 하나의 배포판 `orca-keychron` 안에 두 Python 패키지를 둔다.

- `src/orca_keychron`: Orca 상태 수집, 표시 루프, 키보드 제어와 내비게이션을 소유한다.
- `src/orca_keychron_gjc`: GJC 관찰 훅, 프로토콜, 수신기, 슬롯 추적, 설치와 전용 CLI를 소유한다.

`pyproject.toml`에 선언된 CLI 진입점은 다음과 같다.

```toml
[project.scripts]
orca-keychron = "orca_keychron.cli:main"
orca-keychron-gjc = "orca_keychron_gjc.cli:main"
```

합의된 GJC CLI 이름은 `orca-keychron-gjc`이다.

현재 파서에 선언된 하위 명령은 다음과 같다.

| CLI | 하위 명령 |
|---|---|
| `orca-keychron` | `status`, `probe`, `run`, `setup`, `autostart`, `preview` |
| `orca-keychron-gjc` | `setup`, `run`, `serve`, `status`, `clear`, `install`, `uninstall`, `doctor`, `autostart` |

## 소스 레이아웃

`rg --files src/orca_keychron src/orca_keychron_gjc`로 확인한 패키지 파일 경계다.

```text
src/orca_keychron/
  __init__.py
  __main__.py
  autostart.py
  cli.py
  config.py
  device_lock.py
  digit_hold.py
  indicator.py
  keychron_hid.py
  models.py
  orca_navigation.py
  orca_status.py
  permissions.py
  rendering.py
  worktree_tracker.py

src/orca_keychron_gjc/
  __init__.py
  __main__.py
  autostart.py
  cli.py
  config.py
  gjc_install.py
  gjc_protocol.py
  gjc_source.py
  gjc_tracker.py
  assets/
    decision-parent.md
    decision-worker.md
    gjc_hook.ts
```

`setuptools.packages.find`는 `src` 아래 두 패키지를 찾고, `tool.setuptools.package-data`는 `orca_keychron_gjc/assets/*.ts`와 `*.md`를 배포 대상에 포함하도록 선언한다. 실제 빌드 산출물 포함 여부는 별도 검증 대상이다.

## 의존 방향

의존 방향은 `orca_keychron_gjc`에서 `orca_keychron`으로만 향한다.

1. `orca_keychron_gjc.cli`는 코어의 `Indicator`, `KeychronDevice`, Orca 명령 조회, 권한 확인과 렌더링 색상을 사용한다.
2. `GjcStatusSource`는 Unix 소켓 입력을 검증한 뒤 `GjcTracker`에 전달한다.
3. `GjcTracker`는 검증된 현재 스냅샷을 표시용 `GjcIndicator`로 집계한다.
4. 코어의 `Indicator`는 GJC를 조회하지 않고 `GjcStatusSource.indicators()`가 제공하는 현재 상태를 그린다.
5. 협력적 키보드 소유권 잠금, 숫자 키 선택과 Orca 패널 이동은 각각 코어의 `KeychronDevice`, `Indicator`, `OrcaWorktreeTabNavigator` 경로에서 처리한다.

GJC 패키지는 HID, 렌더링 또는 Orca 내비게이션을 복제하지 않는다. 코어 패키지는 GJC 프로토콜이나 설치 모듈을 임포트하지 않는다.

## 공유 계약

실제 클래스 선언에서 확인한 공유 경계는 다음과 같다.

- `orca_keychron.models.DisplayIndicator`: `identity_label`, `state`, `slot`, `target_pane_keys`, `agent_count`를 제공한다.
- `orca_keychron.indicator.PushedStatusSource`: `command`, `start()`, `stop()`, `indicators(now=None)`를 제공한다.
- `orca_keychron_gjc.gjc_tracker.GjcIndicator`: 표시 계약의 필드와 함께 `pending_requests`, `connected`를 보유한다.
- `orca_keychron_gjc.gjc_source.GjcStatusSource`: 수신기 생명주기와 표시 목록을 제공한다.

두 패키지가 공유하는 것은 이 표시·수신 경계다. GJC의 `launch_id`를 Orca의 `worktree_id`로 바꾸어 저장하지 않는다.

## receiver와 실행 경계

- `run`은 `GjcStatusSource`와 shared `Indicator`를 함께 실행해 로컬 socket 수신, LED 표시, Orca pane navigation을 제공한다.
- `serve`는 `GjcStatusSource`만 실행한다. HID를 열지 않으며, private local AF_UNIX endpoint 밖의 원격 session을 모으지 않는다.
- receiver 또는 transport가 재시작되어 같은 publisher가 reconnect하면 registry의 launch/slot을 이어갈 수 있다. 새 `gjc` process의 `Publisher`는 새 UUID를 만들므로 동일 launch를 이어가지 않는다.
- GJC autostart module은 Orca LaunchAgent conflict를 검사한다. 기존 Orca `autostart.py`에는 반대 방향의 GJC 검사 코드가 없으므로 mutual check라고 표현하지 않는다.
- `KeychronDevice`의 lock은 같은 구현을 사용하는 process 사이의 cooperative exclusion이다. arbitrary external HID writer를 차단하지 않는다.

## 네이티브 훅 설치 경계

- 사용자 범위 기본 루트: `~/.gjc/agent`
- 프로젝트 범위 루트: `<project>/.gjc`
- 관리 로더: `hooks/pre/orca-keychron.ts`
- 관리 decision worker: `agents/keychron-decision-worker.md`
- 관리 매니페스트: `.orca-keychron/manifest.json`
- immutable release: `.orca-keychron/releases/<sha256>/gjc_hook.ts`, `decision-parent.md`
- 복구 journal: `.orca-keychron/transaction.json` (transaction 진행 중에만 존재)
- 관리 에셋 원본: `src/orca_keychron_gjc/assets/`

설치기는 소유 파일만 관리하고, 사용자와 프로젝트 범위가 한 GJC 프로세스에 함께 로드되어도 publisher는 하나만 유지해야 한다. 상세 설치·프로토콜 의미는 `docs/gjc-bridge-contract.md`를 따른다.

## 설정과 hook schema

- `setup`이 저장한 absolute socket path는 explicit `--socket`이 없을 때 `install`, `run`, `serve`, `status`, `doctor`가 공유한다. custom endpoint는 setup 후 install 순서로 적용하고, 변경 시 loader를 다시 설치한다.
- `config.json`과 `registry.json`은 private runtime directory에 저장되고, receiver socket은 같은 directory의 `bridge.sock`가 기본이다.
- decision worker의 `yield` 호출은 bare envelope가 아니라 `result.data`에 `needs_user_decision` envelope를 둔다. hook은 runtime tool result의 `details.data`에서 이를 읽는다.
- `waiting > failed > working > unknown > done > idle` 우선순위를 적용한다. 빈 zone key의 하늘색 기본 렌더링과 할당된 launch의 `idle` 상태는 서로 다른 개념이다.
