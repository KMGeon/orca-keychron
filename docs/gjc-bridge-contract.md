# GJC 브리지 구현 계약

상태: 2026-09-06 구현 계약. 실제 실행한 검증과 미검증 범위는 [최종 검증 기록](gjc-validation.md)과 [하드웨어 검증 기록](gjc-hardware-validation.md)에 구분한다. 이 계약 자체는 전역 설치나 배포 완료를 뜻하지 않는다.

제품 경계는 Orca/GJC 표시 모드 선택, 사용자·프로젝트 범위 설치, 안정적인 슬롯 배정과 overflow 노출을 포함한다.

## 소유권과 구성 요소

GJC 네이티브 훅은 프로세스 내부 관찰 모델을 유지한다. GJC 프로세스마다 publisher 하나가 대화형 root와 네이티브 child session을 묶는다. Python Unix socket receiver는 완전 스냅샷을 검증하고, tracker는 안정적인 슬롯과 표시 우선순위를 계산한다. 기존 하드웨어·렌더링·Orca 내비게이션 계층은 공통 표시 형태만 소비하며 기존 Orca 집계는 유지한다. Renderer tick은 push된 상태만 소비하고 GJC를 조회하지 않는다.

Orca 안에서 사용자가 실행하는 명령은 계속 `gjc`다. Root 등록에는 실제 Orca pane metadata와 대화형 context가 필요하다. 테스트 fixture에서만 `ORCA_KEYCHRON_ALLOW_HEADLESS=1`로 print mode를 허용한다. 같은 프로세스의 native child session은 이미 등록된 root에 합류한다.

Header의 cwd/PID로 parent를 추측하거나 모든 child factory를 새 root로 취급하지 않는다. 임의의 중첩 CLI 프로세스와 SDK-only host는 상속된 Orca metadata로 새 root를 주장할 수 없다. 전용 wrapper는 선택적 진단 수단이며 사용자 실행 파일을 대체하는 필수 경로가 아니다.

## Wire protocol v1

전송은 private AF_UNIX socket의 JSON Lines다. Heartbeat와 재연결을 포함해 모든 frame은 현재 관찰 모델 전체를 담은 스냅샷이다. Prompt, question, answer, tool argument/result, credential 또는 임의 error text는 전송하지 않는다.

```json
{
  "version": 1,
  "type": "snapshot",
  "producerId": "uuid of process publisher",
  "sequence": 1,
  "launchId": "uuid of root GJC invocation",
  "pid": 123,
  "startedAt": 1788632000000,
  "complete": true,
  "closed": false,
  "root": {
    "sessionId": "actual current root session id",
    "terminalHandle": "term_...",
    "paneKey": "tab:leaf",
    "worktreeId": "actual Orca worktree id"
  },
  "sessions": [
    {
      "sessionId": "actual session id",
      "role": "root",
      "state": "working",
      "pendingAsks": 0,
      "pendingDecisions": 0
    }
  ]
}
```

허용 상태는 `idle`, `working`, `waiting`, `done`, `failed`, `paused`, `cancelled`, `unknown`, `closed`다. `waiting`은 관찰된 미해결 ask 또는 검증된 decision handoff를 뜻하며, 모든 GJC approval UI를 관찰할 수 있다는 보장은 아니다. `closed=true`는 명시적인 root shutdown만 뜻하며 socket EOF를 뜻하지 않는다.

### Publisher

- 상태 변경 시와 2초마다 스냅샷을 보낸다.
- 제한된 backoff로 재연결하고, 연결 직후 최신 완전 스냅샷을 보낸다.
- Backpressure에서는 무제한 이력을 쌓지 않고 최신 상태로 병합한다.
- Timer와 socket은 GJC 프로세스의 종료를 막지 않는다. 정상 root shutdown에는 제한 시간 내 flush를 수행한다.
- 제한은 session 256개, session당 active tool call 128개, frame 512 KiB, identifier 512자다.
- 관찰 한도를 넘으면 `complete=false`로 표시한다. 일부만 남기고 정상 상태로 보이면 안 된다.
- 사용자 범위와 프로젝트 범위 hook이 한 프로세스에 함께 로드되면 중복 publisher를 억제한다.

### Receiver와 registry

Receiver lease는 local monotonic receive time 기준 8초다. Socket EOF 또는 lease 만료 시 해당 launch는 `unknown`이 되며 슬롯은 유지된다. 같은 producer의 이전 sequence는 최신 데이터를 덮어쓰지 못한다. 더 새로운 유효한 complete snapshot은 관찰 모델 전체를 교체하므로 sequence gap을 복구하지만, hook이 받지 못한 event까지 복구하지는 못한다. 바뀐 producer는 다른 live launch를 탈취할 수 없다.

Registry에는 검증된 표시 데이터만 원자적으로 mode `0600`으로 저장한다. 복원된 record는 live complete snapshot이 도착할 때까지 `unknown`이다. 명시적인 root shutdown은 해당 launch와 슬롯을 자연스럽게 해제한다. Overflow는 기존 배정을 옮기지 않고 status 목록에 노출하며, 유효한 해제 뒤에만 빈 슬롯으로 승격한다. 수동 `clear`는 연결이 끊긴 launch의 local PID에 `os.kill(pid, 0)`을 실행하여 `ESRCH`/`ProcessLookupError`로 process death를 확인한 경우에만 허용한다. 연결 중인 producer(lease 만료 포함), 살아 있는 PID, 권한 거부, 유효하지 않거나 판단 불가능한 local PID는 보수적으로 거절한다. EOF와 lease 만료만으로는 죽음을 입증하지 못하며 force 옵션은 제공하지 않는다. 거절 시 launch, slot, registry, tombstone을 변경하지 않고 후속 heartbeat도 계속 처리한다. 존재하지 않는 launch의 clear는 변경 없는 no-op이다.

Control은 receiver thread에서 producer frame과 직렬 처리하며 canonical UUID만 허용한다. 성공 응답은 `{version:1,type:"response",ok:true,cleared:boolean,status:...}`이고, clear 거절은 `{version:1,type:"response",ok:false,cleared:false,error:{code:"clear_refused",reason:...},status:...}`이다. `reason`은 `connected`, `process_alive`, `process_death_unconfirmed` 중 하나다. `request_control`은 성공/거절별 정확한 필드 집합과 타입, error code/reason, 기존 status registry schema를 검증한다. Status 요청에는 성공 응답만 허용하고 `cleared`/`error`는 포함하지 않는다. CLI는 clear 거절 사유와 보존 사실을 표시하고 exit 1을 반환하며, bridge 연결 실패와 구별한다. `--json`도 동일한 거절 응답과 nonzero exit를 반환한다.

## 상태 해석

Publisher 내부 pending ask 식별자는 `(sessionId, toolCallId)`다. 대응하는 tool/runtime start/end 쌍은 중복 집계하거나 해결된 call을 다시 열 수 없다. Root 완료는 child의 ask/decision을 지우지 않는다.

- 성공한 최종 assistant `stop`은 앞선 tool error를 회복할 수 있다.
- Assistant `error`는 `failed`, `aborted`는 `cancelled`다.
- `toolUse`만 있는 외부 `agent_end=completed`는 `unknown`이다.
- Pause, maintenance, retry와 queued work는 `done`이 아니다.
- Child의 성공한 `yield`는 검증된 yield result로 판단한다. Child shutdown만으로 성공 처리하지 않는다.
- Retry 중에는 이전의 일시적 terminal failure를 지우고 새로운 최종 결과를 기다린다.

Live complete snapshot의 우선순위는 `unresolved human request -> failed -> working -> unknown/paused/cancelled -> done -> idle`이다. 연결이 unknown이면 stale snapshot의 상태보다 우선한다.

Live incomplete snapshot도 관찰된 unresolved human request, failed, working의 우선순위는 유지한다. 이 세 상태가 없으면 done/idle로 확정하지 않고 unknown으로 표시하며, status의 complete=false로 관측 한도 초과를 함께 알린다. 따라서 관측 불완전은 이미 확인한 사람 호출을 숨기지 않는다.

표시 매핑은 `waiting=orange`, `working=yellow`, `done=green`, `failed=red`다. `unknown`에는 구별 가능한 별도 색을 사용하고 `idle`은 독립 상태로 둔다. 기존 Orca 색상과 동작은 유지한다. Status 목록은 내용 노출 없이 pending request 수와 incomplete coverage를 설명한다.

## Python API 경계

모든 GJC 브리지 모듈은 `src/orca_keychron_gjc/` 아래에 둔다.

### `gjc_protocol.py`

- 불변 dataclass: `GjcRoot`, `GjcSession`, `GjcSnapshot`
- 파서: `parse_snapshot(payload) -> GjcSnapshot`
- 오류: `GjcProtocolError`

### `gjc_tracker.py`

- 생성자: `GjcTracker(max_slots, registry_path=None, lease_seconds=8)`
- 메서드: `apply(snapshot, now=None)`, `disconnect(producer_id, now=None)`, `indicators(now=None)`, `status(now=None)`, `clear(launch_id)`
- `GjcIndicator` 필드: `launch_id`, `state`, `slot`, `target_pane_keys`, `agent_count`, `pending_requests`, `connected`

Tracker는 receiver와 renderer에서 안전하게 호출할 수 있어야 한다. 공통 표시 protocol을 사용하되 worktree ID를 launch ID로 바꾸어 쓰지 않는다.

### `gjc_source.py`

- 생성자: `GjcStatusSource(socket_path, command, max_slots=12, registry_path=None)`
- 경계: `.command`, `.start()`, `.stop()`, `.indicators(now=None)`, `.status(now=None)`

Receiver connection과 tracker 하나를 소유한다. `orca-keychron-gjc status`는 private registry를 읽을 수 있으며 offline/stale record임을 표시해야 한다. 두 번째 receiver는 live socket을 unlink하지 않고 실패해야 한다. Client와 buffer 수를 제한하고 `stop()`에서 receiver thread를 종료한다.

### `config.py`와 `cli.py`

`config.py`는 `Config`, `ConfigError`, `config_dir()`, `config_path()`, `socket_path()`, `registry_path()`, `effective_socket_path()`, `load_config()`, `parse_config()`, `save_config()`를 제공한다.

`cli.py`는 `orca-keychron-gjc` 진입점과 `setup`, `run`, `serve`, `status`, `clear`, `install`, `uninstall`, `doctor`, `autostart` 하위 명령을 정의한다.

## 설치와 source 경계

관리 TypeScript는 `src/orca_keychron_gjc/assets/gjc_hook.ts`에 패키징한다. 설치 대상 loader는 `hooks/pre/orca-keychron.ts`이며, CLI는 `orca-keychron-gjc install`과 `orca-keychron-gjc uninstall`이다.

- 사용자 범위 native hook 기본 루트는 `~/.gjc/agent`다.
- 프로젝트 범위 native hook 루트는 `<project>/.gjc`다.
- Loader는 GJC 0.16.4 adapter의 runtime tool event를 사용하고 literal wildcard hook file을 덮어쓰지 않는다.
- Installer는 소유하지 않은 충돌 파일을 거부하고 dry-run을 지원한다.
- Installer는 기존 설정을 보존하고, 설치 뒤 수정되었거나 소유하지 않은 파일의 제거를 거부한다.
- Loader 설정에는 socket path만 넣고 credential을 복사하지 않는다.
- 배포 전 built wheel에 package asset이 실제 포함되는지 검증해야 한다.

의사결정 지침은 `src/orca_keychron_gjc/assets/decision-parent.md`와 `decision-worker.md`에 분리한다. Child는 검증된 `needs_user_decision` 결과를 yield하고, parent는 사용자에게 질문한 뒤 request ID와 답으로 재개하거나 process restart 뒤 successor를 시작한다. 이는 지원되는 tool composition과 model instruction이며 자동 GJC permission broker가 아니다. 진단과 문서는 이 증거 경계를 유지해야 한다.
