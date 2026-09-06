# GJC 모드 사용자 가이드 (`orca-keychron-gjc`)

Orca 터미널에서 실행한 [가재코드(GJC)](https://github.com/Yeachan-Heo/gajae-code)의 관측 가능한 상태를 Keychron 숫자열 LED에 표시하고, `Option` + 표시 키로 해당 Orca 터미널 패널을 여는 모드입니다.

현재 네이티브 훅은 GJC `0.16.4`에 고정되어 있습니다. 실제 설치는 `gjc --version`이 정확히 `gjc/0.16.4`인지 확인하며, `--dry-run`만 이 검사를 강제하지 않습니다.

## 1. 동작 범위

- Orca 환경 변수 `ORCA_TERMINAL_HANDLE`, `ORCA_PANE_KEY`, `ORCA_WORKTREE_ID`가 있는 대화형 `gjc` 프로세스 하나를 launch 하나로 등록합니다.
- 같은 프로세스의 하위 세션은 별도 키를 차지하지 않고 루트 launch에 집계됩니다.
- `/new`처럼 같은 프로세스 안에서 루트 세션이 바뀌어도 launch는 유지됩니다.
- 수신기 재시작이나 소켓 재연결은 저장된 launch/슬롯을 복원할 수 있습니다. 반면 새 `gjc` 프로세스는 새 launch ID를 만들므로 이전 프로세스와 같은 launch나 슬롯을 보장하지 않습니다.
- 단축키는 자식 대화상자가 아니라 launch의 Orca 부모 패널로 이동합니다.

macOS에서는 Orca가 맨 앞에 있을 때 `Option`과 숫자열의 `1`~`0`, `-`, `=` 키를 함께 누르면 해당 슬롯으로 이동합니다. 길게 누를 필요가 없으며, 같은 키를 다시 선택하려면 한 번 놓았다가 누릅니다. 다른 앱이 맨 앞에 있거나 `Shift`·`Control`·`Command`를 함께 누른 경우에는 이 단축키가 입력을 가로채지 않습니다.

훅은 수신한 런타임 이벤트만 요약합니다. 외부 확장의 확인창과 입력 UI를 모두 관찰하거나, 모델이 의사결정 지침을 반드시 지킨다고 보장하지 않습니다.

## 2. 설치와 실행

요구 사항은 macOS, Python 3.9 이상, `uv`, USB로 연결한 호환 Keychron 키보드, GJC 0.16.4입니다. 블루투스 연결은 필요한 raw HID 인터페이스를 보통 제공하지 않습니다.

소켓을 별도로 지정할 계획이면 `setup`에서 먼저 저장하십시오. 이후 인자를 생략한 `install`, `run`, `serve`, `status`, `doctor`는 저장된 소켓을 사용합니다.

```bash
# 1. 키보드와 KC_RGB 지원을 확인하고 설정 및 소켓을 저장
orca-keychron-gjc setup
# 사용자 소켓을 쓴다면: orca-keychron-gjc setup --socket /absolute/path/bridge.sock

# 2. 같은 소켓으로 설치 계획을 확인한 뒤 훅 설치
orca-keychron-gjc install --dry-run
orca-keychron-gjc install

# 3. 기존 gjc 프로세스를 종료하고 다시 시작한 뒤 포그라운드 실행
orca-keychron-gjc run
```

`setup` 뒤 소켓을 바꾸면 새 설정과 loader가 일치하도록 `install`을 다시 실행해야 합니다. 설치된 훅은 새로 시작한 GJC 프로세스부터 로드됩니다.

로그인 서비스를 사용하려면 포그라운드 `run`을 먼저 `Ctrl-C`로 종료하십시오.

```bash
orca-keychron-gjc autostart install
orca-keychron-gjc autostart status
```

정상적으로 로드되면 `GJC login autostart installed and loaded`가 표시됩니다.

## 3. 상태와 슬롯

| 집계 상태 | LED | 의미 |
|---|---|---|
| `waiting` | 주황색 | 관측된 미해결 `ask` 또는 검증된 의사결정 요청 |
| `failed` | 빨간색 | 관측된 턴/워커 실패 |
| `working` | 노란색 | 모델, 도구 또는 큐 작업 진행 중 |
| `unknown` | 흰색 | 불완전한 관측, pause/cancel, 연결 또는 lease 만료 |
| `done` | 초록색 | 현재 턴 응답 종료. 전체 목표 완료는 아님 |
| `idle` | 하늘색 | 할당된 launch가 입력 대기 상태 |

집계 우선순위는 `waiting > failed > working > unknown > done > idle`입니다. 할당되지 않은 표시 키도 renderer 기본값 때문에 하늘색이지만, 이것은 `idle` launch가 있다는 뜻이 아닙니다.

관측 한도를 넘어 `complete=false`인 경우에도 이미 확인한 승인 대기·실패·작업 중 상태는 해당 색으로 표시합니다. 이런 상태가 없을 때는 완료나 입력 대기로 단정하지 않고 `unknown`으로 표시합니다. 예를 들어 일부 자식을 관측하지 못했더라도 확인된 승인 요청이 하나 있으면 주황색이며, `status`에는 관측이 불완전하다는 표시가 함께 나옵니다. 연결이 끊긴 경우에는 이전 상태 대신 `unknown`을 표시합니다.

수신기는 마지막 유효 스냅샷 뒤 8초 동안의 lease를 사용합니다. 연결이 끊기거나 lease가 만료되면 launch를 지우지 않고 `unknown`으로 표시합니다. 재연결한 동일 publisher는 같은 배정을 이어가며, 빈 슬롯이 생기면 overflow launch가 기존 배정을 밀어내지 않고 그 슬롯을 받습니다.

명시적인 root shutdown(`closed: true`)은 해당 슬롯을 반환합니다. 수동 `clear`는 연결이 끊긴 launch에 대해 OS에서 프로세스 종료가 확인된 경우에만 회수를 허용합니다. 연결 중이거나, 프로세스가 살아 있거나, 권한 문제 등으로 종료 여부가 불확실하면 이유를 표시하고 거부합니다. 단지 `unknown`이거나 lease가 만료된 것만으로 회수하지 않습니다.

```bash
orca-keychron-gjc status
orca-keychron-gjc clear <launch_id>
```

## 4. 명령어

다음 목록은 현재 `--help`에 등록된 명령입니다.

| 명령 | 용도 |
|---|---|
| `setup` | 키보드/KC_RGB를 확인하고 LED, 제품, Orca 명령, 소켓 설정 저장 |
| `run` | 로컬 훅 스냅샷 수신, LED 렌더링, Orca 패널 내비게이션 실행 |
| `serve` | HID와 LED 없이 로컬 Unix 소켓 receiver와 registry tracker만 실행 |
| `status` | live receiver를 조회하고, 연결할 수 없으면 registry를 offline/unknown으로 표시 |
| `clear` | 연결이 끊기고 프로세스 종료가 확인된 launch 회수. receiver가 실행 중이어야 함 |
| `install` / `uninstall` | 소유한 GJC 훅 파일을 설치하거나 가역적으로 제거 |
| `doctor` | GJC 버전, 설정, 훅, receiver, autostart 상태 진단 |
| `autostart` | GJC LaunchAgent의 `install`, `uninstall`, `status` 수행 |

`serve`는 현재 호스트의 private AF_UNIX endpoint를 수신할 뿐입니다. 원격 호스트나 여러 Orca 인스턴스의 세션을 모으는 서비스가 아닙니다.

전체 옵션은 해당 하위 명령의 도움말로 확인하십시오.

```bash
orca-keychron-gjc <command> --help
```

## 5. Orca 모드와 함께 사용할 때

`orca-keychron`과 `orca-keychron-gjc`는 서로 협력하는 프로세스끼리 공유 lock을 사용하므로 둘을 동시에 실행하지 마십시오. 이 lock은 Keychron Launcher나 다른 임의 HID writer까지 차단하는 보안 또는 운영체제 수준의 독점 장치는 아닙니다.

GJC autostart 설치기는 현재/레거시 Orca LaunchAgent가 설치 또는 로드되어 있으면 설치를 거부합니다. 반대 방향의 Orca autostart 설치기는 GJC 서비스를 대칭적으로 검사하지 않으므로, 어느 방향이든 기존 서비스를 먼저 제거한 뒤 전환해야 합니다.

```bash
# Orca 모드 -> GJC 모드
orca-keychron autostart uninstall
orca-keychron-gjc autostart install

# GJC 모드 -> Orca 모드
orca-keychron-gjc autostart uninstall
orca-keychron autostart install
```

포그라운드 실행도 autostart 설치 전에 직접 종료해야 합니다.

## 6. 의사결정 워커

설치기는 opt-in `keychron-decision-worker`를 함께 배치합니다. 이 agent의 선언 도구는 `read`, `yield`뿐이며, 프롬프트 기반 제한이 임의 모델의 준수나 별도 실행 환경의 권한을 보장하지는 않습니다.

하위 워커는 bare JSON이 아니라 `yield` 인자의 `result.data`에 의사결정 envelope를 넣어야 합니다.

```json
{
  "result": {
    "data": {
      "status": "needs_user_decision",
      "request_id": "unique-request-id",
      "question": "어느 옵션으로 진행할까요?",
      "options": ["옵션 A", "옵션 B"],
      "checkpoint": "현재까지 확인한 내용과 답변 뒤 이어갈 작업"
    }
  }
}
```

부모는 실제 child ID의 전체 결과를 읽고, 같은 `request_id`로 사용자에게 질문한 뒤, 답이 있을 때만 실제 child를 resume합니다. GJC 프로세스를 재시작하면 이전 in-memory child는 보통 재개할 수 없으므로 새 successor를 시작해야 하며, 원래 child가 재개됐다고 기록하면 안 됩니다.

## 7. 저장 위치와 제거

GJC runtime 기본 디렉터리는 macOS에서 `~/Library/Application Support/orca-keychron/gjc/`, 그 밖의 플랫폼에서는 `$XDG_CONFIG_HOME/orca-keychron/gjc/` 또는 `~/.config/orca-keychron/gjc/`입니다. 여기에는 `config.json`, `bridge.sock`, `registry.json`, autostart 로그가 저장됩니다.

사용자 범위 훅 루트는 `--agent-dir`, `GJC_CODING_AGENT_DIR`, `~/.gjc/agent` 순으로 결정됩니다. 프로젝트 범위는 `--scope project --project <path>`가 가리키는 `<path>/.gjc`입니다. 설치기는 선택된 root 아래 자신이 소유한 loader, decision worker, release asset, manifest만 관리하며 수정되거나 소유하지 않은 파일은 덮어쓰거나 삭제하지 않습니다.

```bash
orca-keychron-gjc doctor
orca-keychron-gjc uninstall --dry-run
orca-keychron-gjc uninstall
```

`uninstall`은 훅 파일만 제거합니다. 실제 GJC 0.16.4와 격리된 fixture provider로 상태 전송, 다중 자식 의사결정, 재연결, `/new`·세션 재개·종료를 검증했습니다. [런타임 검증 결과](../experiments/gjc-product-qa/REPORT.md)를 참고하십시오.

Q65 Max에서는 실제 상태 renderer가 만든 다섯 RGB 프레임의 펌웨어 응답과 기존 조명 복구를 확인했습니다. Orca 대상 패널 이동과 원래 패널 복귀도 별도로 확인했습니다. 색상을 눈으로 확인하는 검사, 실제 `Option`+숫자 키 입력, 실제 모델의 의사결정 지침 준수는 검증하지 않았습니다. [하드웨어 검증 기록](gjc-hardware-validation.md)에 실행 범위와 증거를 구분해 두었습니다.
