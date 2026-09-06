# 개발 티켓: Orca 내 GJC launch를 Keychron LED로 표시

상태: 구현과 실제 GJC 0.16.4 런타임 검증 자료가 있다. Q65 Max의 RGB 프레임 응답·조명 복구와 Orca 패널 이동을 별도로 검증했다. 실제 키 입력·육안 색상 확인·실제 모델 지침 준수는 미검증이다.

## 1. 목표와 경계

[GJC 0.16.4](https://github.com/Yeachan-Heo/gajae-code)를 Orca 터미널에서 실행할 때, 코어 수정 없이 native hook이 관측한 상태를 로컬 receiver로 보내고 launch별 Keychron 슬롯에 표시한다. `Option` + 표시 키는 해당 launch의 Orca 부모 패널을 연다.

이 기능은 다음을 보장하지 않는다.

- GJC가 노출하지 않은 확장 confirmation/input UI까지 모두 관찰하는 것
- prompt로 선언한 `read`/`yield` 제한을 모든 모델과 실행 환경에서 강제하는 것
- 협력하지 않는 Keychron Launcher 또는 임의 HID writer를 배제하는 것
- Q65 열거 및 macOS 권한 확인만으로 물리 GJC E2E가 완료됐다고 판단하는 것

## 2. 구현 계약

### 네이티브 훅 설치

- user root는 `--agent-dir`, `GJC_CODING_AGENT_DIR`, `~/.gjc/agent` 순으로 선택한다. project root는 `<project>/.gjc`다.
- 선택된 root에서 관리하는 공개 경로는 `hooks/pre/orca-keychron.ts`, `agents/keychron-decision-worker.md`, `.orca-keychron/manifest.json`이다.
- immutable asset은 `.orca-keychron/releases/<sha256>/gjc_hook.ts`와 `decision-parent.md`에 두고 loader가 해당 release를 import한다. `.orca-keychron/transaction.json`은 중단 복구 중에만 존재하는 journal이다.
- 설치/삭제는 manifest가 소유권과 digest를 증명하는 파일만 변경하고, 충돌·사용자 수정·unsafe path는 거부한다. 새로 만드는 관리 디렉터리는 `0700`, 관리 파일은 `0600`을 사용하며 기존 GJC root 전체의 mode를 임의로 바꾸지 않는다.
- 실제 install은 `gjc/0.16.4`를 요구하며 `--dry-run`은 파일을 변경하지 않는다.

### 소켓과 설정

- runtime 기본 디렉터리는 macOS의 `~/Library/Application Support/orca-keychron/gjc/`, 또는 `$XDG_CONFIG_HOME/orca-keychron/gjc/`/`~/.config/orca-keychron/gjc/`다.
- `setup`은 `config.json`에 선택한 absolute socket path를 저장한다. `install`, `run`, `serve`, `status`, `doctor`는 명시적 `--socket`이 없으면 이 값을 사용해야 한다.
- custom socket을 쓰는 경우 `setup`을 먼저 실행하고 그 설정으로 hook을 설치한다. socket 변경 뒤에는 install을 다시 실행해 loader endpoint를 맞춘다.
- AF_UNIX socket은 user-owned mode `0600`, config/registry 파일은 `0600`, runtime 디렉터리는 `0700`이어야 한다.
- `serve`는 로컬 receiver와 registry tracker만 실행하며 HID를 열거나 원격 Orca 세션을 집계하지 않는다.

### launch와 수명

- 대화형 root `gjc` 프로세스마다 publisher/launch ID 하나를 두고, 사용 가능한 경우 슬롯 하나를 배정한다. same-process child와 `/new` session은 launch에 집계된다.
- receiver restart와 transport reconnect는 persisted identity/slot을 이어갈 수 있다. 새 `gjc` 프로세스는 새 launch ID를 만들며 기존 launch 슬롯 승계를 보장하지 않는다.
- receiver lease는 마지막 유효 프레임의 local monotonic time 기준 8초다. EOF/lease 만료는 launch를 `unknown`으로 만들지만 회수하지 않는다.
- explicit root shutdown(`closed: true`)은 슬롯을 회수한다. 수동 `clear`는 OS 수준에서 종료가 확인된 launch만 허용하고, live 또는 단지 disconnected/unknown인 launch는 거부해야 한다.
- overflow launch는 기존 슬롯을 탈취하지 않고 빈 슬롯이 생길 때 배정된다.

### 상태와 렌더링

집계 우선순위는 다음과 같다.

```text
waiting > failed > working > unknown > done > idle
```

색상은 순서대로 주황, 빨강, 노랑, 흰색, 초록, 하늘색이다. `done`은 관측된 현재 턴 종료이지 사용자 목표 완료가 아니다. 할당되지 않은 zone key도 renderer 기본값으로 하늘색이지만 `idle` launch로 집계되지는 않는다.

snapshot의 `complete`는 hook이 알고 있는 모델이 잘리지 않았다는 표시다. GJC에서 전달되지 않은 event나 UI까지 완전하게 관찰했다는 뜻이 아니다.

### 협력적 HID와 autostart

- 두 orca-keychron 모드는 같은 cooperative device lock을 획득한 뒤 Keychron HID를 연다. 이는 같은 lock을 사용하는 프로세스 간 중복 소유만 막는다.
- GJC autostart installer는 현재/레거시 Orca LaunchAgent가 설치 또는 로드된 경우 거부한다.
- Orca base autostart installer는 GJC를 대칭적으로 검사하지 않는다. 따라서 전환은 방향과 무관하게 기존 foreground process와 기존 LaunchAgent를 먼저 종료/제거한 후 수행한다.

### 의사결정 worker

- opt-in `keychron-decision-worker`의 선언 도구는 `read`, `yield`다.
- decision payload는 bare JSON이 아니라 `yield` 인자의 `result.data` 아래 `status`, `request_id`, `question`, `options`, `checkpoint`를 담는다.
- parent는 실제 child ID의 전체 결과를 읽고 같은 request ID로 root `ask`를 수행한 뒤, 실제 답이 있을 때만 그 child를 resume한다.
- GJC process restart 뒤 기존 in-memory child가 사라졌다면 checkpoint와 답을 가진 successor를 시작하고 원래 child를 resume했다고 주장하지 않는다.

## 3. 수용 기준과 검증 상태

- CLI surface는 `setup`, `run`, `serve`, `status`, `clear`, `install`, `uninstall`, `doctor`, `autostart`와 각 `--help`에 일치해야 한다.
- wire protocol, installer ownership, reconnect/registry, priority와 navigation은 repository tests 및 review artifacts로 검증한다. 테스트 통과를 물리 keyboard 또는 실제 model E2E로 표현하지 않는다.
- `clear`가 live/ambiguous launch를 거부하고 closed/provably-dead launch만 회수하는지 source와 process-level test로 검증해야 한다.
- `docs/gjc-validation.md`에는 실제 실행한 소프트웨어·패키지 검증과 미검증 범위를 구분한다. 전역 로그인 서비스 활성화, 실제 키 입력·육안 색상, 실제 provider/model 지침 준수까지 확인했다고 표현하지 않는다. 하드웨어 명령 응답·패널 이동 증거는 `docs/gjc-hardware-validation.md`, 실제 GJC와 fixture provider 검증은 `experiments/gjc-product-qa/REPORT.md`에 둔다.

관련 설계 자료: [hook 실험](gjc-hook-experiment-results.md), [bridge 계약](gjc-bridge-contract.md), [package layout](gjc-package-layout.md), [관찰 설계](gjc-observation-design.md).
