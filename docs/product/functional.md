# 기능 요구사항

> 자동 생성 문서 · 편집 원본: [requirements.json](requirements.json)
> 수정 후 `python scripts/requirements.py --write`로 갱신합니다.

[전체 안내](README.md) · [의사결정](decisions.md) · [기능](functional.md) · [비기능](nonfunctional.md) · [테스트 연결](test-map.md)

이 보기에는 **29개**가 포함됩니다. 같은 요구사항이 기능과 품질 조건을 함께 가지면 두 보기에 나타나지만 ID와 원본은 하나입니다.
수용 기준은 요구하는 동작입니다. 실제 검증 범위는 각 항목의 테스트 연결과 한계를 함께 읽습니다.

| ID | 영역 | 요구사항 |
|---|---|---|
| [R01](#r01) | 호환성 | GJC 0.16.4 고정 지원 |
| [R02](#r02) | 설치 경로 | 사용자·프로젝트 root 선택 |
| [R03](#r03) | 설치 자산 | 불변 release와 최소 loader |
| [R04](#r04) | 설치 안전성 | 증명된 소유 파일만 변경 |
| [R06](#r06) | 설치 수명주기 | 비변경 dry-run과 hook 제거 |
| [R08](#r08) | 소켓 설정 | 저장 socket의 일관된 상속 |
| [R09](#r09) | CLI | 전용 9개 명령과 진단 |
| [R10](#r10) | 수신 서비스 | serve의 로컬 전용 경계 |
| [R12](#r12) | 자동 시작 | GJC 서비스의 독립·보수적 소유 |
| [R13](#r13) | launch 식별 | 대화형 root당 publisher 하나 |
| [R15](#r15) | 세션 수명 | 같은 프로세스의 session 전환 |
| [R16](#r16) | 중복 hook | user·project loader 중복 억제 |
| [R17](#r17) | 요청 상관관계 | pending ask 중복 방지 |
| [R18](#r18) | 의사결정 보존 | 미해결 human request 유지 |
| [R19](#r19) | yield 해석 | 검증된 yield만 성공 인정 |
| [R20](#r20) | 턴 상태 | 최종 outcome과 retry 해석 |
| [R21](#r21) | 의사결정 도구 | opt-in worker와 root-only 지침 |
| [R22](#r22) | 의사결정 재개 | 실제 child와 답의 정확한 상관 |
| [R23](#r23) | 재시작 후 승계 | 사라진 child의 successor 전환 |
| [R31](#r31) | lease | 정확한 8초 monotonic lease |
| [R33](#r33) | registry·slot | 원자 registry와 안정적 slot |
| [R35](#r35) | launch 종료 | 명시적 close만 slot 반환 |
| [R36](#r36) | 수동 회수 | OS로 종료가 증명된 launch만 clear |
| [R37](#r37) | control API | 엄격하고 직렬화된 control |
| [R38](#r38) | 상태 조회 | live·offline 상태의 명확한 구분 |
| [R39](#r39) | 상태 우선순위 | 사람 요청 우선 집계 |
| [R40](#r40) | LED 표시 | 상태별 색상과 빈 slot 표시 |
| [R43](#r43) | Orca 이동 | launch의 부모 pane으로 이동 |
| [R44](#r44) | 키보드 단축키 | 1~0,-,= 단축키와 입력 보존 |

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


<a id="r02"></a>
## R02 · 사용자·프로젝트 root 선택

사용자 hook root는 명시적 agent dir, `GJC_CODING_AGENT_DIR`, 기본 `~/.gjc/agent` 순으로 선택하고 프로젝트 root는 `<project>/.gjc`로 분리해야 한다.

**수용 기준**

- 명시적 `--agent-dir`이 환경 변수보다 우선한다.
- 명시적 경로가 없으면 환경 변수, 그 다음 기본 사용자 경로를 사용한다.
- project scope는 지정 프로젝트의 `.gjc`만 관리한다.

**지원·검증 한계**

- 사용자·프로젝트 hook의 서로 다른 socket 설정 충돌 전체 조합은 별도 운영 점검이 필요하다.

[테스트와 구현 위치](test-map.md#r02) · 결정: [D20](decisions.md#d20)


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


<a id="r08"></a>
## R08 · 저장 socket의 일관된 상속

setup은 absolute socket path를 저장하고 install, run, serve, status, doctor는 명시적 override가 없을 때 그 값을 사용해야 한다.

**수용 기준**

- 상대 socket path는 거부되고 absolute path만 저장된다.
- 공백과 nondefault zone이 있는 저장 socket으로 실제 CLI 경계가 동작한다.
- socket 변경 뒤 재설치하면 loader endpoint가 새 설정과 일치한다.
- 명시적 `--socket`은 해당 명령에서 저장값보다 우선한다.

**지원·검증 한계**

- 모든 명령과 모든 override 조합의 완전한 조합표 검증은 아니다.

[테스트와 구현 위치](test-map.md#r08) · 결정: [D19](decisions.md#d19)


<a id="r09"></a>
## R09 · 전용 9개 명령과 진단

`orca-keychron-gjc`는 setup, run, serve, status, clear, install, uninstall, doctor, autostart와 각 도움말을 제공하고 doctor는 주요 구성요소의 건강 상태를 분리해 진단해야 한다.

**수용 기준**

- 9개 하위 명령이 parser와 설치된 entrypoint 도움말에 노출된다.
- doctor는 GJC 버전, config, hook, receiver, autostart 상태를 각각 보고한다.
- 부분 장애를 전체 healthy로 표시하지 않는다.
- 패키지 버전을 CLI에서 확인할 수 있다.

**지원·검증 한계**

- doctor의 GJC와 launchctl은 integration test에서 로컬 stub을 사용한다.

[테스트와 구현 위치](test-map.md#r09) · 결정: [D18](decisions.md#d18) · [D19](decisions.md#d19)


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


<a id="r13"></a>
## R13 · 대화형 root당 publisher 하나

실제 Orca pane metadata가 있는 대화형 root GJC 프로세스마다 publisher와 launch를 하나만 만들고 native child는 그 launch에 집계해야 한다.

**수용 기준**

- root 등록에는 terminal handle, pane key, worktree ID와 대화형 context가 필요하다.
- headless root 허용은 명시적 fixture opt-in에서만 가능하다.
- 같은 프로세스의 native child는 별도 launch나 슬롯을 만들지 않는다.
- 독립 GJC 프로세스는 서로 다른 launch가 된다.

**지원·검증 한계**

- 모든 native host의 대화형 identity 순서를 포괄하지 않는다.

[테스트와 구현 위치](test-map.md#r13) · 결정: [D03](decisions.md#d03) · [D04](decisions.md#d04)


<a id="r15"></a>
## R15 · 같은 프로세스의 session 전환

같은 GJC 프로세스의 `/new`와 resume는 root session만 바꾸고 launch, publisher, slot과 미해결 요청을 유지해야 하며 새 프로세스는 새 identity를 가져야 한다.

**수용 기준**

- `/new` 뒤 producer와 launch ID 및 slot이 유지된다.
- resume 뒤 이전 root session으로 돌아가도 같은 publisher를 사용한다.
- session 전환 중 기존 미해결 child 요청이 사라지지 않는다.
- 새 OS 프로세스는 이전 launch 승계를 보장하지 않는다.

**지원·검증 한계**

- 모든 GJC event ordering 변형을 보장하지 않는다.

[테스트와 구현 위치](test-map.md#r15) · 결정: [D03](decisions.md#d03)


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


<a id="r17"></a>
## R17 · pending ask 중복 방지

pending ask는 `(sessionId, toolCallId)`로 식별하고 중복·지연 start/end가 count를 늘리거나 해결된 call을 다시 열지 못하게 해야 한다.

**수용 기준**

- 같은 session과 call ID의 반복 start는 한 건으로 집계된다.
- matching tool name과 call ID의 실제 종료만 pending을 해제한다.
- 해결된 call의 늦은 start가 pending을 다시 만들지 않는다.
- bounded resolved history가 소진되면 `complete=false`로 불확실성을 드러낸다.

**지원·검증 한계**

- 모든 runtime/tool event permutation에 대한 형식 증명은 아니다.

[테스트와 구현 위치](test-map.md#r17) · 결정: [D13](decisions.md#d13)


<a id="r18"></a>
## R18 · 미해결 human request 유지

parent 완료나 child shutdown은 미해결 ask·decision을 지우지 않으며 상관된 실제 답만 해당 handoff를 해결해야 한다.

**수용 기준**

- parent가 done이어도 child의 pending request가 waiting 우선순위를 유지한다.
- child shutdown만으로 decision을 해결하지 않는다.
- 여러 답 중 request ID와 child correlation이 맞는 한 건만 해제한다.
- answer-before-decision 또는 충돌한 답은 false resolution을 만들지 않는다.

**지원·검증 한계**

- runtime scenario의 답과 model 동작은 deterministic fixture가 제공한다.

[테스트와 구현 위치](test-map.md#r18) · 결정: [D11](decisions.md#d11) · [D13](decisions.md#d13) · [D16](decisions.md#d16)


<a id="r19"></a>
## R19 · 검증된 yield만 성공 인정

child의 성공이나 decision은 유효한 yield `result.data`를 검증해 판단하고 malformed result나 child shutdown만으로 green 처리하지 않아야 한다.

**수용 기준**

- 유효한 yield success만 child 성공으로 인정한다.
- 유효한 `needs_user_decision` envelope만 decision waiting으로 인정한다.
- malformed yield는 `unknown`으로 표시한다.
- shutdown 단독은 success가 아니다.

**지원·검증 한계**

- 모든 향후 GJC yield schema 변형을 지원하지 않는다.

[테스트와 구현 위치](test-map.md#r19) · 결정: [D14](decisions.md#d14)


<a id="r20"></a>
## R20 · 최종 outcome과 retry 해석

최종 assistant stop, error, aborted와 retry·pause·maintenance·queued 상태를 구분하고 임시 tool 실패만으로 최종 상태를 확정하지 않아야 한다.

**수용 기준**

- 최종 assistant stop은 앞선 tool error 뒤에도 done으로 회복할 수 있다.
- assistant error는 failed, aborted는 cancelled로 해석한다.
- toolUse만 있는 외부 completed는 unknown이다.
- retry, pause, maintenance와 queued work는 done이 아니다.
- retry가 소진되고 outstanding tool이 끝나도 기존 최종 failed를 잘못 지우지 않는다.

**지원·검증 한계**

- 모든 native maintenance·자동 retry event 순서를 열거한 검증은 아니다.

[테스트와 구현 위치](test-map.md#r20) · 결정: [D14](decisions.md#d14)


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


<a id="r22"></a>
## R22 · 실제 child와 답의 정확한 상관

parent는 실제 child 전체 결과와 request ID를 사용해 root에서 질문하고 실제 답이 있을 때만 그 child를 checkpoint와 함께 재개해야 한다.

**수용 기준**

- parent가 축약하거나 추측한 ID가 아니라 실제 child ID를 읽는다.
- root ask는 child가 보낸 원래 request ID를 사용한다.
- 선택 답, request ID, checkpoint가 모두 일치할 때만 실제 child를 resume한다.
- 취소나 다른 요청의 답을 승인으로 사용하지 않는다.

**지원·검증 한계**

- fixture provider가 올바른 답을 공급하므로 실제 모델 instruction-following은 증명하지 않는다.

[테스트와 구현 위치](test-map.md#r22) · 결정: [D16](decisions.md#d16) · [D23](decisions.md#d23)


<a id="r23"></a>
## R23 · 사라진 child의 successor 전환

GJC 프로세스 재시작 뒤 이전 in-memory child가 없으면 checkpoint와 답을 전달한 별도 successor를 시작하고 원래 child를 재개했다고 기록하지 않아야 한다.

**수용 기준**

- 이전 in-memory child를 재개할 수 없는 경우 checkpoint와 실제 답을 명시적으로 전달한 별도 successor를 시작한다.
- successor는 원래 child와 구분되는 identity를 사용한다.
- parent는 해당 요청의 checkpoint와 실제 답을 이어받을 작업에 전달한다. 임의로 답을 만들거나 원래 child가 재개됐다고 주장하지 않는다.
- 인계 결과에 successor 경로임을 명시한다.

**지원·검증 한계**

- 답과 checkpoint는 harness가 명시적으로 프로세스 사이에 전달하며 자동 durable recovery는 제공하지 않는다.

[테스트와 구현 위치](test-map.md#r23) · 결정: [D17](decisions.md#d17)


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


<a id="r35"></a>
## R35 · 명시적 close만 slot 반환

`closed=true`인 명시적 root shutdown만 launch와 slot을 자연 해제하고 EOF나 retired launch의 늦은 frame은 회수·부활을 일으키지 않아야 한다.

**수용 기준**

- 유효한 closed snapshot은 해당 launch와 slot을 제거한다.
- socket EOF와 process kill은 unknown으로만 전환하고 slot을 유지한다.
- closure 뒤 overflow가 vacancy에 승격될 수 있다.
- retired launch의 지연·재전송 frame은 부활하지 않는다.

**지원·검증 한계**

- 비정상 종료는 명시적 close로 간주하지 않는다.

[테스트와 구현 위치](test-map.md#r35) · 결정: [D09](decisions.md#d09)


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


<a id="r38"></a>
## R38 · live·offline 상태의 명확한 구분

status는 live receiver 응답을 우선하고 연결 실패 시 private registry를 offline source로 읽어 stale record를 unknown으로 표시하며 count, overflow와 incomplete coverage를 content 없이 보여줘야 한다.

**수용 기준**

- live bridge가 있으면 정확한 control status를 표시한다.
- bridge가 없으면 registry 출처와 offline/stale임을 명시한다.
- offline record의 과거 working·waiting·done을 live 상태처럼 표시하지 않고 unknown으로 강등한다.
- agent count, pending count, overflow와 incomplete coverage를 노출한다.
- Python 3.9에서도 transport timeout이 bounded error로 끝난다.

**지원·검증 한계**

- 상태 조회는 prompt나 답변 내용 자체를 제공하지 않는다.

[테스트와 구현 위치](test-map.md#r38) · 결정: [D10](decisions.md#d10) · [D12](decisions.md#d12) · [D19](decisions.md#d19)


<a id="r39"></a>
## R39 · 사람 요청 우선 집계

launch 상태는 `waiting > failed > working > unknown > done > idle` 순으로 집계하고 disconnect는 stale 상태를 unknown으로 덮으며 incomplete snapshot도 확인된 waiting·failed·working을 숨기지 않아야 한다.

**수용 기준**

- 모든 상태 subset과 session 순서에서 동일한 우선순위를 적용한다.
- unresolved human request는 failure나 working보다 우선한다.
- 연결 끊김과 lease 만료는 stale waiting·done 대신 unknown이다.
- `complete=false`여도 확인된 waiting·failed·working은 유지한다.
- incomplete 상태에 상위 세 상태가 없으면 done/idle이 아니라 unknown이다.

**지원·검증 한계**

- actual mass color 증거는 exact captured snapshot replay이며 그 순간의 live renderer 관측이 아니다.

[테스트와 구현 위치](test-map.md#r39) · 결정: [D11](decisions.md#d11) · [D12](decisions.md#d12) · [D24](decisions.md#d24)


<a id="r40"></a>
## R40 · 상태별 색상과 빈 slot 표시

waiting, failed, working, unknown, done, idle은 각각 주황, 빨강, 노랑, 흰색, 초록, 하늘색으로 표시하고 빈 zone key도 하늘색으로 렌더링하되 idle launch로 집계하지 않아야 한다.

**수용 기준**

- 여섯 상태가 서로 구별되는 지정 palette로 변환된다.
- waiting은 orange, failed는 red, working은 yellow, unknown은 white, done은 green, idle은 sky-blue다.
- 할당되지 않은 표시 키는 sky-blue지만 status에 idle launch를 추가하지 않는다.
- overflow나 음수 slot이 다른 키를 색칠하지 않는다.
- done은 현재 turn 종료만 뜻하고 전체 목표 완료를 뜻하지 않는다.

**지원·검증 한계**

- 빨강 포함 전체 palette의 optical color 검증은 수행하지 않았다.
- hardware 기록은 현재 audit의 새 실행이 아니다.

[테스트와 구현 위치](test-map.md#r40) · 결정: [D11](decisions.md#d11) · [D24](decisions.md#d24) · [D25](decisions.md#d25)


<a id="r43"></a>
## R43 · launch의 부모 pane으로 이동

Option과 표시 키를 선택하면 child나 launch ID가 아니라 해당 launch가 등록한 Orca 부모 pane으로 이동하고 stale·불일치 target에는 dispatch하지 않아야 한다.

**수용 기준**

- GJC indicator는 worktree identity 없이 terminal handle과 pane key로 선택 가능하다.
- 선택 직전에 target이 사라지거나 slot이 재배정되면 이동을 취소한다.
- navigator는 최신 terminal handle을 조회하고 정확한 worktree tab·pane 일치를 확인한다.
- wrong tab 응답이나 stale target에는 switch 명령을 보내지 않는다.

**지원·검증 한계**

- 실제 Option key event tap부터 pane 이동까지의 물리 E2E는 수행하지 않았다.

[테스트와 구현 위치](test-map.md#r43) · 결정: [D03](decisions.md#d03) · [D18](decisions.md#d18) · [D22](decisions.md#d22)


<a id="r44"></a>
## R44 · 1~0,-,= 단축키와 입력 보존

macOS에서 Orca가 frontmost일 때만 Option+`1`~`0`,`-`,`=`을 12개 slot으로 즉시 매핑하고 key release·repeat·재배정을 안전하게 처리하며 다른 앱과 추가 modifier 입력은 통과시켜야 한다.

**수용 기준**

- 숫자열 1~0,-,=의 physical keycode가 slot 1~12에 대응한다.
- Orca가 frontmost이고 유효 target이 있을 때 keydown에서 즉시 선택한다.
- 같은 키 repeat는 keyup 전 target을 추가 이동하지 않는다.
- 다른 앱이 frontmost이거나 Shift, Control, Command가 추가되면 입력을 가로채지 않는다.
- slot 재배정 또는 listener startup failure에서 stale 이동과 native listener 누수를 막는다.

**지원·검증 한계**

- 실제 keyboard layout, Accessibility/Input Monitoring 권한과 물리 key 입력은 미검증이다.

[테스트와 구현 위치](test-map.md#r44) · 결정: [D22](decisions.md#d22) · [D25](decisions.md#d25)
