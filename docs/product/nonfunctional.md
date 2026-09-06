# 비기능 요구사항

> 자동 생성 문서 · 편집 원본: [requirements.json](requirements.json)
> 수정 후 `python scripts/requirements.py --write`로 갱신합니다.

[전체 안내](README.md) · [의사결정](decisions.md) · [기능](functional.md) · [비기능](nonfunctional.md) · [테스트 연결](test-map.md)

이 보기에는 **28개**가 포함됩니다. 같은 요구사항이 기능과 품질 조건을 함께 가지면 두 보기에 나타나지만 ID와 원본은 하나입니다.
수용 기준은 요구하는 동작입니다. 실제 검증 범위는 각 항목의 테스트 연결과 한계를 함께 읽습니다.

| ID | 영역 | 요구사항 |
|---|---|---|
| [R01](#r01) | 호환성 | GJC 0.16.4 고정 지원 |
| [R03](#r03) | 설치 자산 | 불변 release와 최소 loader |
| [R04](#r04) | 설치 안전성 | 증명된 소유 파일만 변경 |
| [R05](#r05) | 설치 복구 | private·transactional 설치 |
| [R06](#r06) | 설치 수명주기 | 비변경 dry-run과 hook 제거 |
| [R07](#r07) | 설정·플랫폼 | 분리된 private 설정과 Python 3.9 |
| [R10](#r10) | 수신 서비스 | serve의 로컬 전용 경계 |
| [R11](#r11) | 배포 패키지 | checkout 독립 wheel |
| [R12](#r12) | 자동 시작 | GJC 서비스의 독립·보수적 소유 |
| [R14](#r14) | lineage 보호 | 중첩 프로세스의 root 사칭 방지 |
| [R16](#r16) | 중복 hook | user·project loader 중복 억제 |
| [R21](#r21) | 의사결정 도구 | opt-in worker와 root-only 지침 |
| [R24](#r24) | wire protocol | 엄격한 full snapshot JSONL v1 |
| [R25](#r25) | 개인정보 보호 | content-free 상태 전송 |
| [R26](#r26) | 전송 신뢰성 | 변경 push와 정확한 2초 heartbeat |
| [R27](#r27) | 전송 자원 | backpressure 병합과 bounded 종료 |
| [R28](#r28) | 관찰 한도 | session·call·frame·ID cap |
| [R29](#r29) | endpoint 보안 | private socket과 안전한 stale 복구 |
| [R30](#r30) | 수신기 자원 | client·buffer 제한과 격리 |
| [R31](#r31) | lease | 정확한 8초 monotonic lease |
| [R32](#r32) | 수신 일관성 | sequence·generation 회귀 방지 |
| [R33](#r33) | registry·slot | 원자 registry와 안정적 slot |
| [R34](#r34) | 소유권 복구 | process crash와 endpoint 분리 |
| [R36](#r36) | 수동 회수 | OS로 종료가 증명된 launch만 clear |
| [R37](#r37) | control API | 엄격하고 직렬화된 control |
| [R41](#r41) | 렌더러 자원 | push-only 표시와 실패 복구 |
| [R42](#r42) | HID 상호 배제 | 공유 cooperative device lock |
| [R45](#r45) | 증거·문서 | 검증 층과 미검증 경계의 분리 |

<a id="r01"></a>
## R01 · GJC 0.16.4 고정 지원

제품은 수정하지 않은 일반 `gjc/0.16.4` 실행을 지원하고, 실제 설치에서는 다른 버전을 변경 전에 거부해야 한다.

**수용 기준**

- `gjc --version`이 정확히 `gjc/0.16.4`일 때만 실제 hook 설치가 진행된다.
- 사용자는 필수 wrapper나 upstream GJC 수정 없이 `gjc`를 직접 실행한다.
- `--dry-run`은 버전 설치 여부와 무관하게 계획을 확인할 수 있다.

**지원·검증 한계**

- GJC 0.16.4 이외 버전은 지원하지 않는다.
- 실제 provider/model 준수는 검증하지 않았다.

[테스트와 구현 위치](test-map.md#r01) · 결정: [D01](decisions.md#d01) · [D02](decisions.md#d02)


<a id="r03"></a>
## R03 · 불변 release와 최소 loader

설치기는 loader, decision worker, manifest와 SHA-256 release 자산을 정해진 경로에 배치하고 loader에는 socket path만 기록해야 한다.

**수용 기준**

- release 경로는 자산 digest로 식별되고 manifest가 관리 파일과 digest를 기록한다.
- 재설치는 동일 상태에서 멱등이며 upgrade는 이전 소유 release를 제거한다.
- loader 설정에 credential이나 대화 내용이 포함되지 않는다.

**지원·검증 한계**

- 임의 환경 변수와 모든 오류 로그까지 포괄하는 credential 누출 검사는 아니다.

[테스트와 구현 위치](test-map.md#r03) · 결정: [D20](decisions.md#d20)


<a id="r04"></a>
## R04 · 증명된 소유 파일만 변경

설치와 제거는 manifest와 digest로 소유권이 증명된 변경되지 않은 파일만 수정하며 충돌, 사용자 수정, symlink와 unsafe path는 보존하고 거부해야 한다.

**수용 기준**

- 소유하지 않은 충돌 파일을 덮어쓰거나 삭제하지 않는다.
- 설치 후 사용자가 수정한 관리 파일은 보존하고 작업을 실패시킨다.
- symlink, FIFO 등 안전하지 않은 경로를 따라가거나 변경하지 않는다.
- 기존 GJC root 전체 권한을 임의로 바꾸지 않는다.

**지원·검증 한계**

- 협력적 파일 잠금은 hostile same-user TOCTOU를 완전히 배제하는 보안 경계가 아니다.

[테스트와 구현 위치](test-map.md#r04) · 결정: [D20](decisions.md#d20)


<a id="r05"></a>
## R05 · private·transactional 설치

새 관리 디렉터리는 0700, 파일은 0600으로 만들고 journal을 사용해 실패나 중단 뒤 기존 설치를 복구할 수 있어야 한다.

**수용 기준**

- umask와 무관하게 새 관리 디렉터리 체인은 0700이고 관리 파일은 0600이다.
- upgrade 실패 시 모든 관리 byte가 이전 상태로 rollback된다.
- 남은 transaction journal은 다음 실행에서 검증 후 복구된다.
- 복구 중 사용자 변경을 발견하면 보존적으로 중단한다.

**지원·검증 한계**

- 모든 파일시스템과 전원 손실 checkpoint의 crash consistency를 증명하지는 않는다.

[테스트와 구현 위치](test-map.md#r05) · 결정: [D20](decisions.md#d20)


<a id="r06"></a>
## R06 · 비변경 dry-run과 hook 제거

dry-run은 지원 GJC가 없어도 변경 없이 계획을 보여주고, uninstall은 소유한 hook 자산만 제거하며 설정과 서비스는 유지해야 한다.

**수용 기준**

- dry-run 전후 관리 root의 byte와 metadata가 동일하다.
- dry-run은 GJC 0.16.4 설치를 요구하지 않는다.
- uninstall은 소유한 loader, worker, release, manifest만 제거한다.
- uninstall dry-run도 변경하지 않는다.

**지원·검증 한계**

- 전역 서비스 제거는 uninstall의 책임이 아니다.

[테스트와 구현 위치](test-map.md#r06) · 결정: [D20](decisions.md#d20)


<a id="r07"></a>
## R07 · 분리된 private 설정과 Python 3.9

GJC 모드는 기존 Orca 모드와 분리된 runtime 설정을 사용하고 저장 경로와 파일을 private하게 유지하며 Python 3.9 이상에서 동작해야 한다.

**수용 기준**

- GJC config, socket, registry 경로가 기존 Orca 모드 경로와 분리된다.
- 설정 디렉터리는 0700이고 config는 0600이다.
- 잘못되거나 unsafe한 config는 typed error로 거부되고 자동 덮어쓰지 않는다.
- 배포물의 Python 요구 버전은 3.9 이상이며 frozen suite가 3.9와 3.13에서 통과한 기록이 있다.

**지원·검증 한계**

- 실제 Ubuntu runner 실행은 수행하지 않았다.

[테스트와 구현 위치](test-map.md#r07) · 결정: [D18](decisions.md#d18) · [D19](decisions.md#d19)


<a id="r10"></a>
## R10 · serve의 로컬 전용 경계

serve는 현재 호스트의 local receiver와 registry tracker만 실행하며 HID, 렌더러, 외부 Orca 명령, 원격 집계를 시작하지 않아야 한다.

**수용 기준**

- serve는 private AF_UNIX endpoint를 열고 status 요청에 응답한다.
- serve 과정에서 HID 모듈을 열거나 외부 명령을 시작하지 않는다.
- 충돌한 live endpoint를 보존하고 bounded error로 종료한다.
- 종료 시 receiver thread와 소켓 자원을 정리한다.

**지원·검증 한계**

- serve는 원격 host나 여러 Orca instance를 집계하지 않는다.

[테스트와 구현 위치](test-map.md#r10) · 결정: [D02](decisions.md#d02) · [D19](decisions.md#d19)


<a id="r11"></a>
## R11 · checkout 독립 wheel

built wheel은 두 CLI entrypoint와 현재 Python·TypeScript·지침 asset을 포함하고 checkout import 없이 fresh 환경에서 동작해야 한다.

**수용 기준**

- wheel 안의 package 파일과 asset byte가 현재 배포 입력과 일치한다.
- `orca-keychron`과 `orca-keychron-gjc` 도움말이 격리 설치에서 실행된다.
- 설치된 loader가 checkout 대신 wheel 자산을 사용해 receiver로 snapshot을 보낸다.
- Python 3.9 fresh 환경에서 dependency check와 isolated import가 성공한 동결 기록이 있다.

**지원·검증 한계**

- 문서화된 frozen wheel digest는 현재 파일을 새로 빌드했다는 의미가 아니다.

[테스트와 구현 위치](test-map.md#r11) · 결정: [D18](decisions.md#d18)


<a id="r12"></a>
## R12 · GJC 서비스의 독립·보수적 소유

GJC autostart는 별도 namespace를 사용하고 현재 또는 legacy Orca 서비스가 설치·로드된 상태에서는 변경 없이 거부하며 실패 시 이전 소유 상태를 복원해야 한다.

**수용 기준**

- GJC LaunchAgent label과 파일이 기존 Orca 서비스와 분리된다.
- 현재·legacy Orca 서비스의 설치 또는 load를 발견하면 fail closed한다.
- 비소유·수정 plist는 보존한다.
- bootstrap 실패 시 새 파일을 제거하거나 이전 소유 plist와 load 상태를 복원한다.

**지원·검증 한계**

- 실제 login LaunchAgent 활성화는 수행하지 않았다.
- 기존 Orca installer는 GJC 서비스를 대칭 검사하지 않으므로 전환은 수동 절차가 필요하다.

[테스트와 구현 위치](test-map.md#r12) · 결정: [D21](decisions.md#d21) · [D25](decisions.md#d25)


<a id="r14"></a>
## R14 · 중첩 프로세스의 root 사칭 방지

중첩 CLI나 SDK-only host는 상속된 Orca metadata, cwd 또는 PID header만으로 새 root 권한을 주장할 수 없어야 한다.

**수용 기준**

- 상속된 owner marker를 가진 nested process는 새 root를 등록하지 않는다.
- child가 현재 root ID를 다시 열어도 switch, mutation, shutdown 권한을 얻지 않는다.
- 관련 없는 loader가 재사용 ID로 live root를 탈취하지 못한다.
- cwd/PID만으로 parent-child를 추론하지 않는다.

**지원·검증 한계**

- 별도 actual GJC nested CLI/SDK 실행 전체 조합을 검증한 것은 아니다.

[테스트와 구현 위치](test-map.md#r14) · 결정: [D03](decisions.md#d03) · [D04](decisions.md#d04)


<a id="r16"></a>
## R16 · user·project loader 중복 억제

사용자와 프로젝트 hook이 같은 GJC 프로세스에 함께 로드되어도 publisher와 launch는 하나이며 이벤트와 pending count가 중복 집계되지 않아야 한다.

**수용 기준**

- 두 loader가 같은 owner process에서 하나의 publisher를 공유한다.
- 동일 이벤트를 두 loader가 받아도 pending count가 한 번만 반영된다.
- session switch 전후 delivery 순서가 바뀌어도 중복 root가 생기지 않는다.

**지원·검증 한계**

- 서로 다른 hook 버전이나 socket 설정 충돌은 지원 범위가 아니다.

[테스트와 구현 위치](test-map.md#r16) · 결정: [D05](decisions.md#d05)


<a id="r21"></a>
## R21 · opt-in worker와 root-only 지침

decision worker는 opt-in으로 배치되고 선언 도구를 read와 yield로 제한하며 parent 지침은 기존 prompt를 대체하지 않고 root에만 추가되어야 한다.

**수용 기준**

- 설치된 worker 선언에는 `read`와 `yield`만 있다.
- decision payload는 bare JSON이 아니라 `yield.result.data` envelope를 사용한다.
- parent guidance는 기존 system prompt를 보존해 append된다.
- parent guidance는 child session에 중복 적용되지 않는다.

**지원·검증 한계**

- prompt 선언은 모든 모델·host의 권한을 강제하는 permission broker가 아니다.

[테스트와 구현 위치](test-map.md#r21) · 결정: [D15](decisions.md#d15) · [D16](decisions.md#d16) · [D23](decisions.md#d23)


<a id="r24"></a>
## R24 · 엄격한 full snapshot JSONL v1

wire는 version 1의 불변 full snapshot JSON Lines만 허용하고 정확한 schema, UTF-8 encoding, 고유 session과 허용 상태를 검증해야 한다.

**수용 기준**

- 각 heartbeat와 변경 frame이 현재 관찰 모델 전체를 담는다.
- 필수 필드·타입·상태가 다르거나 확장 필드·중복 JSON key가 있으면 거부한다.
- session ID는 snapshot 안에서 고유하고 root session은 정확히 하나다.
- UTF-8 JSON line만 허용하며 BOM과 UTF-16/32를 거부한다.

**지원·검증 한계**

- 합성 event producer를 사용하므로 모든 실제 GJC native event를 포괄하지 않는다.

[테스트와 구현 위치](test-map.md#r24) · 결정: [D06](decisions.md#d06) · [D07](decisions.md#d07)


<a id="r25"></a>
## R25 · content-free 상태 전송

wire, persisted registry와 status에는 prompt, 질문·답, option, checkpoint, tool argument/result, credential 또는 임의 error text를 저장하거나 표시하지 않아야 한다.

**수용 기준**

- 전송 schema는 식별자, 상태, count와 표시 metadata의 allowlist만 허용한다.
- 민감 필드 sentinel이 JSONL frame, registry와 human/JSON status에 나타나지 않는다.
- 알 수 없는 content 확장 필드는 parser가 거부한다.
- actual GJC evidence도 metadata-only로 기록된다.

**지원·검증 한계**

- 명시한 wire·registry·status 밖의 임의 외부 로그까지 비밀 부재를 보장하지 않는다.

[테스트와 구현 위치](test-map.md#r25) · 결정: [D07](decisions.md#d07) · [D23](decisions.md#d23)


<a id="r26"></a>
## R26 · 변경 push와 정확한 2초 heartbeat

publisher는 상태 변경 시와 기본 2초마다 full snapshot을 보내고 bounded reconnect 뒤 현재 최신 상태만 즉시 전송해야 한다.

**수용 기준**

- 상태 변경은 다음 2초 heartbeat를 기다리지 않고 publish된다.
- 기본 heartbeat interval은 정확히 2초이며 test override도 2초 상한을 넘지 않는다.
- 재연결 backoff는 bounded하고 최대 2초다.
- 연결 직후 stale history가 아니라 최신 full snapshot 한 상태를 보낸다.

**지원·검증 한계**

- runtime scenario는 정확한 2초 elapsed-time SLO를 측정하지 않는다.
- 상태 변경 push는 무지연 보장이 아니다.

[테스트와 구현 위치](test-map.md#r26) · 결정: [D06](decisions.md#d06)


<a id="r27"></a>
## R27 · backpressure 병합과 bounded 종료

backpressure에서는 무제한 history를 쌓지 않고 최신 상태로 병합하며 timer와 socket이 GJC 종료를 막지 않고 정상 shutdown을 제한 시간 안에 flush해야 한다.

**수용 기준**

- write backpressure 중 보류 frame 수와 buffer가 bounded하다.
- drain 뒤 가장 최신 full snapshot만 전달된다.
- receiver가 없어도 publisher process가 자연 종료한다.
- stalled receiver에서도 shutdown이 bounded하게 끝난다.
- 명시적 close는 가능하면 마지막 closed snapshot을 flush한다.

**지원·검증 한계**

- 모든 운영체제 kernel buffer 크기와 장기 stalled-reader 패턴을 포괄하지 않는다.

[테스트와 구현 위치](test-map.md#r27) · 결정: [D06](decisions.md#d06)


<a id="r28"></a>
## R28 · session·call·frame·ID cap

publisher와 receiver는 session 256개, session당 active call 128개, UTF-8 frame 512 KiB, identifier 512자의 정확한 한도를 적용하고 초과 시 `complete=false` 또는 명시적 거부로 false completeness를 막아야 한다.

**수용 기준**

- 최대 256 sessions와 session당 128 active calls까지 표현한다.
- 512 KiB 이하 UTF-8 frame은 허용하고 초과 frame은 해당 client에서 거부한다.
- identifier는 512자까지 허용하고 제어문자나 초과 길이를 거부한다.
- publisher가 관찰 항목을 더 담을 수 없으면 `complete=false`를 보낸다.
- resolved receipt history 소진도 정상 complete로 가장하지 않는다.

**지원·검증 한계**

- 관찰 cap은 모든 GJC UI를 볼 수 있다는 의미가 아니며 초과 시 일부 상태는 unknown이다.

[테스트와 구현 위치](test-map.md#r28) · 결정: [D07](decisions.md#d07) · [D12](decisions.md#d12)


<a id="r29"></a>
## R29 · private socket과 안전한 stale 복구

socket, registry와 runtime path는 현재 사용자 소유의 private mode여야 하며 두 번째 receiver나 stale 복구가 live·foreign·교체된 경로를 unlink, chmod 또는 덮어쓰지 않아야 한다.

**수용 기준**

- runtime 디렉터리는 0700, socket과 registry는 0600이다.
- 두 번째 receiver는 live socket을 보존하고 실패한다.
- stale socket은 소유권이 증명될 때만 복구한다.
- bind/stop 중 path가 교체되면 replacement를 변경하지 않는다.
- symlink와 foreign inode는 거부한다.

**지원·검증 한계**

- same-user hostile path replacement를 완전히 배제하는 보안 sandbox는 아니다.

[테스트와 구현 위치](test-map.md#r29) · 결정: [D08](decisions.md#d08)


<a id="r30"></a>
## R30 · client·buffer 제한과 격리

receiver는 최대 32 client와 client별 frame buffer를 제한하고 malformed·partial·idle client를 격리하며 stop 시 receiver thread를 종료해야 한다.

**수용 기준**

- 동시에 관리하는 client 수는 32를 넘지 않는다.
- client buffer는 512 KiB frame 한도를 넘겨 자라지 않는다.
- malformed 또는 non-UTF-8 client 하나가 다른 정상 publisher를 중단시키지 않는다.
- partial stall과 idle client는 capacity를 영구 점유하지 않는다.
- stop은 listener와 receiver thread를 bounded하게 정리한다.

**지원·검증 한계**

- 테스트는 cap과 timeout을 작게 주입한 조합도 포함하며 장기 부하 benchmark는 아니다.

[테스트와 구현 위치](test-map.md#r30) · 결정: [D08](decisions.md#d08)


<a id="r31"></a>
## R31 · 정확한 8초 monotonic lease

receiver는 마지막 유효 frame의 local monotonic receive time부터 정확히 8초 lease를 적용하고 EOF나 만료 시 slot을 유지한 채 launch를 unknown으로 표시해야 한다.

**수용 기준**

- 8초 이전에는 마지막 live 상태가 유지되고 deadline부터 unknown이 된다.
- socket EOF는 즉시 unknown으로 만들되 slot을 회수하지 않는다.
- producer wall clock 값은 lease를 연장하지 않는다.
- 재연결한 동일 producer의 최신 frame은 preserved slot을 회복한다.

**지원·검증 한계**

- 8초 lease는 process death 증명이 아니므로 수동 clear 권한을 주지 않는다.

[테스트와 구현 위치](test-map.md#r31) · 결정: [D09](decisions.md#d09)


<a id="r32"></a>
## R32 · sequence·generation 회귀 방지

receiver는 같은 producer의 오래된 sequence를 거부하고 새 full frame으로 history를 교체하며 바뀐 identity나 obsolete connection이 live launch를 탈취·disconnect하지 못하게 해야 한다.

**수용 기준**

- 낮거나 같은 stale sequence가 최신 상태를 덮어쓰지 못한다.
- 새로운 complete frame은 sequence gap 뒤에도 전체 상태를 교체한다.
- producer 또는 launch metadata가 바뀐 frame은 live launch를 탈취하지 못한다.
- 새 connection이 owner가 된 뒤 이전 connection close는 false disconnect를 만들지 않는다.
- retired generation은 slot에 부활하지 않는다.

**지원·검증 한계**

- 모든 scheduler 수준 race interleaving을 완전 탐색한 것은 아니다.

[테스트와 구현 위치](test-map.md#r32) · 결정: [D09](decisions.md#d09)


<a id="r33"></a>
## R33 · 원자 registry와 안정적 slot

registry는 검증된 표시 상태를 private file에 원자 저장하고 재시작 시 fresh frame 전까지 unknown을 유지하며 기존 slot과 overflow 순서를 안정적으로 복원해야 한다.

**수용 기준**

- registry replace는 partial JSON을 노출하지 않고 0600 mode를 유지한다.
- 재시작으로 복원한 record는 fresh complete frame 전까지 unknown이다.
- 동일 launch는 reconnect와 receiver restart 뒤 기존 slot을 유지한다.
- overflow는 status에 보이며 유효한 vacancy가 생길 때만 승격한다.
- registry의 손상·unsafe type·capacity mismatch는 보존적으로 거부한다.

**지원·검증 한계**

- 동시 reader가 모든 filesystem에서 항상 같은 atomicity를 보는지에 대한 formal proof는 아니다.

[테스트와 구현 위치](test-map.md#r33) · 결정: [D09](decisions.md#d09)


<a id="r34"></a>
## R34 · process crash와 endpoint 분리

registry와 receiver 소유권은 process crash 뒤 회수 가능해야 하고 서로 다른 endpoint가 같은 registry를 공유해 손상시키지 못하며 stop은 자기 자원만 해제해야 한다.

**수용 기준**

- live owner가 있는 registry는 두 번째 endpoint가 변경하지 못한다.
- 서로 다른 registry를 쓰는 receiver는 독립적으로 실행된다.
- SIGKILL된 owner의 lock은 후속 process가 회수할 수 있고 committed registry는 보존된다.
- restore 또는 receiver start 실패 시 새 ownership을 누수하지 않는다.
- stop은 replacement나 다른 receiver 자원을 제거하지 않는다.

**지원·검증 한계**

- 모든 on-disk crash write interleaving과 전원 손실을 증명하지 않는다.

[테스트와 구현 위치](test-map.md#r34) · 결정: [D08](decisions.md#d08)


<a id="r36"></a>
## R36 · OS로 종료가 증명된 launch만 clear

clear는 disconnected launch의 local PID가 ESRCH로 확인된 경우에만 허용하고 connected, live, ambiguous 또는 invalid PID는 상태를 바꾸지 않고 거부해야 한다.

**수용 기준**

- connected producer는 lease가 만료되어도 clear를 거부한다.
- disconnected PID가 살아 있거나 권한 거부 등으로 불명확하면 거부한다.
- local PID의 `ProcessLookupError` 또는 ESRCH만 death proof로 인정한다.
- 거부 시 launch, slot, registry, tombstone과 후속 heartbeat 처리가 유지된다.
- 존재하지 않는 launch는 변경 없는 no-op이다.

**지원·검증 한계**

- PID reuse를 완전히 방지하는 process identity 보장은 없고 force clear는 제공하지 않는다.

[테스트와 구현 위치](test-map.md#r36) · 결정: [D10](decisions.md#d10)


<a id="r37"></a>
## R37 · 엄격하고 직렬화된 control

control 요청은 canonical UUID와 정확한 response schema를 사용하고 producer frame과 직렬 처리하며 clear 거절, unreachable, absent no-op을 CLI exit와 JSON에서 구분해야 한다.

**수용 기준**

- 비canonical launch UUID는 receiver 접촉 전에 거부한다.
- status 성공, clear 성공, clear 거절 응답은 각자 허용된 정확한 필드와 타입만 가진다.
- clear 거절은 `clear_refused`와 allowed reason을 반환하고 CLI exit 1이 된다.
- bridge unreachable은 clear 거절과 구분된다.
- control과 reconnect frame이 직렬 처리되어 clear된 상태를 stale frame이 부활시키지 않는다.

**지원·검증 한계**

- control protocol은 local private socket의 cooperative same-user boundary다.

[테스트와 구현 위치](test-map.md#r37) · 결정: [D10](decisions.md#d10)


<a id="r41"></a>
## R41 · push-only 표시와 실패 복구

renderer는 receiver가 push한 공통 상태만 소비하고 GJC를 polling하지 않으며 receiver나 HID 실패와 정상 종료 모두에서 조명을 복원하고 자원을 해제해야 한다.

**수용 기준**

- 렌더 tick은 GJC 또는 원격 Orca를 직접 조회하지 않는다.
- source가 push한 model과 local lease expiry만 사용한다.
- source start·read 실패와 HID write 실패에서 이전 조명을 복원한다.
- 실패 뒤 source, HID handle과 cooperative lock을 모두 해제한다.

**지원·검증 한계**

- 실제 USB unplug 및 모든 펌웨어 오류 경로는 미검증이다.

[테스트와 구현 위치](test-map.md#r41) · 결정: [D02](decisions.md#d02) · [D06](decisions.md#d06) · [D18](decisions.md#d18) · [D21](decisions.md#d21)


<a id="r42"></a>
## R42 · 공유 cooperative device lock

Orca 모드와 GJC 모드는 HID open 전에 같은 account-scoped cooperative lock을 획득해 협력 프로세스의 동시 소유를 막고 정상 종료와 SIGKILL 뒤 후속 owner를 허용해야 한다.

**수용 기준**

- lock은 account-scoped private 경로를 사용한다.
- lock 획득 전에는 HID enumeration이나 open을 수행하지 않는다.
- 동시 두 협력 process 중 하나만 ownership을 얻는다.
- 정상 release와 owner SIGKILL 뒤 다른 process가 lock을 얻는다.
- symlink, hardlink, FIFO와 public mode lock path를 거부한다.

**지원·검증 한계**

- Keychron Launcher나 동일 lock을 사용하지 않는 임의 HID writer는 배제하지 못한다.
- 두 실제 HID-owning mode의 동시 물리 실행은 하지 않았다.

[테스트와 구현 위치](test-map.md#r42) · 결정: [D21](decisions.md#d21) · [D25](decisions.md#d25)


<a id="r45"></a>
## R45 · 검증 층과 미검증 경계의 분리

문서는 source/unit/package/runtime/model/hardware 증거를 구분하고 테스트 통과를 모든 approval UI, 보편적 모델 준수, 임의 HID 배제, global service 활성화나 release 완료로 과장하지 않아야 한다.

**수용 기준**

- 최종 감사 문서는 실행한 software/package/runtime gate와 수행하지 않은 경계를 별도 기술한다.
- actual GJC scenario가 deterministic loopback provider이고 실제 모델 검증이 아님을 명시한다.
- hardware 기록은 firmware ACK·복구·pane 이동과 미실행 physical input·optical color를 구분한다.
- global service, provider account, 실제 Ubuntu, commit·PR·release 미수행을 명시한다.
- historical audit 기록을 현재 새 실행으로 표현하지 않는다.

**지원·검증 한계**

- R45는 문서 정확성 요구이며 직접 행동 자동화 테스트로 가장하지 않는다.
- 실제 키 입력·optical color·실제 모델·global service·actual Ubuntu는 미실행이다.

[테스트와 구현 위치](test-map.md#r45) · 결정: [D01](decisions.md#d01) · [D15](decisions.md#d15) · [D23](decisions.md#d23) · [D24](decisions.md#d24) · [D25](decisions.md#d25)
