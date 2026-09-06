# 의사결정 기록

> 자동 생성 문서 · 편집 원본: [decisions.json](decisions.json)
> 수정 후 `python scripts/requirements.py --write`로 갱신합니다.

[전체 안내](README.md) · [의사결정](decisions.md) · [기능](functional.md) · [비기능](nonfunctional.md) · [테스트 연결](test-map.md)

최종 선택과 그 이유를 읽는 문서입니다. 검토했던 대안은 채택 여부를 구분해 남깁니다.
`사용자 제약·합의`는 기존 대화/개발 티켓의 합의, `구현 선택`은 구현 과정의 선택, `검증 후 수정`은 실험·회귀 테스트로 바로잡은 내용입니다.

| ID | 결정 | 상태 |
|---|---|---|
| [D01](#d01) | Orca 안에서 GJC를 그대로 실행 | 채택 |
| [D02](#d02) | 관찰 경로를 native hook으로 정정 | 채택 |
| [D03](#d03) | 프로세스 launch 하나에 슬롯 하나 | 채택 |
| [D04](#d04) | 대화형 Orca root만 launch 소유 | 채택 |
| [D05](#d05) | 중복 hook도 publisher 하나 | 채택 |
| [D06](#d06) | 변경 push와 2초 전체 snapshot | 채택 |
| [D07](#d07) | wire에는 표시용 metadata만 전송 | 채택 |
| [D08](#d08) | 로컬 receiver와 registry를 단일 소유 | 채택 |
| [D09](#d09) | slot은 연결보다 launch에 고정 | 채택 |
| [D10](#d10) | clear는 확인된 dead process에만 허용 | 채택 |
| [D11](#d11) | 사람 요청을 최우선으로 표시 | 채택 |
| [D12](#d12) | 누락과 중단은 unknown으로 보수 처리 | 채택 |
| [D13](#d13) | 질문은 call과 receipt로 상관관계 유지 | 채택 |
| [D14](#d14) | 종료 event와 성공을 분리 | 채택 |
| [D15](#d15) | 의사결정 worker는 opt-in read와 yield만 선언 | 채택 |
| [D16](#d16) | 결정은 parent가 묻고 실제 child만 재개 | 채택 |
| [D17](#d17) | 재시작 뒤에는 successor로 명시적 인계 | 채택 |
| [D18](#d18) | 한 배포판에서 Python 패키지 경계 분리 | 채택 |
| [D19](#d19) | GJC 전용 CLI와 저장된 socket 계약 | 채택 |
| [D20](#d20) | hook 설치는 소유권과 immutable release로 제한 | 채택 |
| [D21](#d21) | 두 mode는 cooperative HID와 별도 service를 사용 | 채택 |
| [D22](#d22) | 숫자 키는 Orca 부모 패널로 이동 | 채택 |
| [D23](#d23) | 모든 승인 UI와 모델 강제 보장은 제외 | 제외 |
| [D24](#d24) | 검증 층을 분리하고 oracle을 같은 시점에 묶음 | 채택 |
| [D25](#d25) | 물리 입력과 real model 검증은 별도 과제로 유지 | 보류 |

<a id="d01"></a>
## D01 · Orca 안에서 GJC를 그대로 실행

**채택 · 사용자 제약·합의**

Orca 터미널을 사용자 작업 위치로 유지하고, 수정하지 않은 GJC 0.16.4를 일반 `gjc` 명령으로 실행한 상태를 지원한다. GJC 코어 수정, 업스트림 PR, 필수 wrapper는 범위에서 제외한다.

**선택한 이유**

- 사용자가 이미 사용하는 Orca 패널과 GJC 실행 흐름을 바꾸지 않아야 한다.
- 설치된 GJC 0.16.4에서 코어 수정 없이 native hook이 실제 로드되고 상태를 전송하는 경로가 확인됐다.
- 지원 버전을 고정해야 hook event 의미와 설치 자산을 검증 가능한 계약으로 유지할 수 있다.

**검토한 대안**

- GJC 코어에 observer API를 추가하고 업스트림 PR을 만드는 안은 사용자 선택과 달라 채택하지 않았다.
- 전용 launcher나 wrapper를 필수 실행 경로로 두는 안은 기존 `gjc` 사용 경험을 바꾸므로 진단용 선택지로만 남겼다.
- GJC 0.16.4 이외 버전까지 호환된다고 간주하는 안은 검증 근거가 없어 채택하지 않았다.

**영향과 한계**

- 실제 install은 `gjc/0.16.4`를 정확히 확인하고, dry-run만 버전 확인 없이 허용한다.
- GJC가 native hook으로 노출하지 않는 상태는 제품이 완전하게 관찰한다고 약속하지 않는다.
- 새 GJC 버전 지원은 별도 adapter와 검증이 필요한 후속 결정이다.

관련 요구사항: [R01](functional.md#r01) · [R45](nonfunctional.md#r45)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md) · [REPORT.md](../../experiments/gjc-product-qa/REPORT.md)


<a id="d02"></a>
## D02 · 관찰 경로를 native hook으로 정정

**채택 · 검증 후 수정**

초기의 filesystem extension 또는 GJC 코어 observer 권고를 폐기하고, GJC 0.16.4의 실제 native `.gjc/hooks` loader가 제공하는 lifecycle과 tool event를 관찰 경로로 사용한다. 화면 scraping과 상태 파일 polling은 사용하지 않는다.

**선택한 이유**

- 일반 filesystem extension discovery는 ordinary GJC 실행에서 로드되지 않는다는 소스 조사가 확인됐다.
- 추가 조사와 실제 실행에서 native hook 경로는 upstream 변경 없이 로드됐다.
- 화면 scraping과 polling은 순간 전이, 질문 상관관계, 재연결 상태를 신뢰성 있게 복구하지 못한다.

**검토한 대안**

- 일반 `.gjc` filesystem extension을 설치하는 초기 가정은 실제 loader 경로와 맞지 않아 폐기했다.
- GJC 코어 observer API 추가안은 기술적으로 더 넓은 관찰이 가능하지만 사용자 범위를 벗어나 채택하지 않았다.
- TUI 화면 scraping이나 최신 상태 파일 polling은 응답 UI를 가리고 상태 전이를 놓칠 수 있어 채택하지 않았다.

**영향과 한계**

- 제품은 hook이 받은 event만 요약하며 확장 confirm/input과 모든 permission UI를 보장하지 않는다.
- renderer는 push된 모델만 소비하고 GJC를 역조회하지 않는다.
- 관찰 누락은 성공으로 추정하지 않고 incomplete 또는 unknown으로 드러낸다.

관련 요구사항: [R01](functional.md#r01) · [R10](functional.md#r10) · [R41](nonfunctional.md#r41)

근거: [gjc-observation-design.md](../../docs/gjc-observation-design.md) · [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md)


<a id="d03"></a>
## D03 · 프로세스 launch 하나에 슬롯 하나

**채택 · 사용자 제약·합의**

대화형 Orca root `gjc` 프로세스마다 publisher와 launch ID를 하나 만들고, 가능한 경우 launch에 슬롯 하나를 배정한다. 같은 프로세스의 native child, 손자, `/new`, resume 세션은 같은 launch에 집계하며 새 프로세스는 새 launch로 취급한다.

**선택한 이유**

- 숫자 키는 프로젝트나 개별 child가 아니라 사용자가 실행한 독립 GJC 작업 창을 대표해야 한다.
- native child event에는 신뢰할 수 있는 `parentSession`이 없었고 cwd, PID header, worktree ID만으로 계층을 추정할 수 없었다.
- 같은 프로세스의 `/new`와 resume에서 launch와 슬롯을 유지하는 실제 런타임 결과가 확인됐다.

**검토한 대안**

- worktree마다 슬롯을 주는 안은 같은 worktree의 독립 실행과 같은 프로세스의 session 전환을 구분하지 못해 채택하지 않았다.
- child나 손자마다 숫자 키를 재배정하는 안은 키 의미가 흔들리고 부모 작업으로 돌아가기 어려워 채택하지 않았다.
- 새 프로세스가 이전 launch와 슬롯을 자동 승계하는 안은 지속 identity 근거가 없어 보장하지 않는다.

**영향과 한계**

- 한 launch의 모든 관측 세션 수와 사람 요청 수를 한 슬롯 상태로 집계한다.
- 새 GJC 프로세스는 같은 cwd나 pane metadata를 가져도 새 launch ID를 만든다.
- 새 프로세스의 이전 슬롯 재사용은 빈 슬롯 배정 결과일 수 있지만 계약상 승계가 아니다.

관련 요구사항: [R13](functional.md#r13) · [R14](nonfunctional.md#r14) · [R15](functional.md#r15) · [R43](functional.md#r43)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [REPORT.md](../../experiments/gjc-product-qa/root-switch/REPORT.md)


<a id="d04"></a>
## D04 · 대화형 Orca root만 launch 소유

**채택 · 구현 선택**

launch 등록은 실제 Orca terminal, pane, worktree metadata와 대화형 root context가 있는 GJC에만 허용한다. headless 등록은 명시적 테스트 fixture opt-in으로 제한하고, 중첩 CLI나 SDK-only host는 상속된 환경만으로 새 root를 주장하지 못하게 한다.

**선택한 이유**

- 상속된 Orca 환경은 nested process에도 전달되므로 존재만으로 사용자 root를 구분할 수 없다.
- root ownership을 고정해야 child factory나 unrelated loader가 슬롯을 바꾸거나 launch를 닫는 일을 막을 수 있다.
- headless 허용을 fixture에만 두면 실제 제품 identity와 테스트 편의를 혼동하지 않는다.

**검토한 대안**

- cwd, PID header 또는 환경 변수 존재만으로 root를 추정하는 안은 child가 부모 표시 소유권을 빼앗을 수 있어 거부했다.
- 모든 session factory를 새 launch로 등록하는 안은 same-process child 집계 계약과 충돌해 거부했다.

**영향과 한계**

- 등록된 root identity와 owner marker가 session switch, completion, shutdown 권한의 기준이 된다.
- 실제 child-process 환경 상속과 SDK-first 순서의 모든 변형은 아직 별도 검증 한계로 남는다.

관련 요구사항: [R13](functional.md#r13) · [R14](nonfunctional.md#r14)

근거: [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-hook-second-audit.md](../../docs/testing/gjc-hook-second-audit.md) · [gjc-requirements-matrix.md](../../docs/testing/gjc-requirements-matrix.md)


<a id="d05"></a>
## D05 · 중복 hook도 publisher 하나

**채택 · 구현 선택**

사용자 범위와 프로젝트 범위 hook이 한 GJC 프로세스에 함께 발견되어도 공유 owner를 통해 publisher 하나와 launch 하나만 유지한다.

**선택한 이유**

- 두 설치 범위를 함께 쓰는 것은 정상 구성이며 중복 상태 전송이나 agent count 증가로 이어지면 안 된다.
- 실제 user/project duplicate discovery에서 unique launch 하나만 만들어지는 결과가 확인됐다.
- event delivery 순서가 바뀌어도 root 권한과 shared publisher identity가 유지돼야 한다.

**검토한 대안**

- 설치 scope마다 별도 publisher를 만드는 안은 같은 프로세스를 두 launch로 표시하므로 거부했다.
- 프로젝트 hook 설치를 금지하는 안은 합의된 user/project 설치 범위를 줄이므로 채택하지 않았다.

**영향과 한계**

- duplicate event는 호출별 identity로 dedupe하고 counts를 두 배로 만들지 않는다.
- 서로 다른 hook 버전이나 socket 설정이 충돌하는 조합은 검증된 정상 duplicate discovery 범위 밖이다.

관련 요구사항: [R16](functional.md#r16)

근거: [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [REPORT.md](../../experiments/gjc-product-qa/REPORT.md) · [gjc-hook-second-audit.md](../../docs/testing/gjc-hook-second-audit.md)


<a id="d06"></a>
## D06 · 변경 push와 2초 전체 snapshot

**채택 · 구현 선택**

publisher는 상태 변경 때와 2초 heartbeat마다 현재 모델 전체를 JSONL snapshot v1으로 push한다. 재연결에는 최신 snapshot만 보내고, backpressure에서는 과거 이력을 쌓지 않고 최신 상태로 병합한다.

**선택한 이유**

- 실제 hook exporter는 ACK 없는 event replay에서 receiver 손실 구간을 복구하지 못했다.
- full snapshot은 sequence gap 뒤에도 최신 관측 모델을 교체해 stale history 의존을 줄인다.
- 주기 polling 없이도 liveness와 lease 갱신을 제공하면서 메모리 사용을 제한해야 한다.

**검토한 대안**

- event history 전체 재전송은 backpressure에서 무제한 큐가 될 수 있어 채택하지 않았다.
- 최신 파일을 반복 읽거나 GJC 상태를 polling하는 안은 순간 전이와 순서를 복구하지 못해 채택하지 않았다.
- 변경 event만 보내고 heartbeat를 생략하는 안은 연결 생존과 lease 갱신을 확인할 수 없어 채택하지 않았다.

**영향과 한계**

- sequence는 오래된 frame의 역행을 막고 새 complete snapshot은 이전 관측 history를 대체한다.
- timer와 socket은 GJC 종료를 붙잡지 않으며 정상 shutdown flush도 제한 시간 안에서만 수행한다.
- heartbeat는 업무 상태를 다시 조회하는 polling이 아니라 같은 현재 snapshot의 전송이다.

관련 요구사항: [R24](nonfunctional.md#r24) · [R26](nonfunctional.md#r26) · [R27](nonfunctional.md#r27) · [R41](nonfunctional.md#r41)

근거: [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [transport-audit-report.md](../../docs/testing/transport-audit-report.md)


<a id="d07"></a>
## D07 · wire에는 표시용 metadata만 전송

**채택 · 구현 선택**

wire, registry, status에는 version, identity, lifecycle state, counters와 연결 상태처럼 표시 계산에 필요한 검증된 metadata만 둔다. prompt, question, answer, tool argument/result, credential, 임의 error text와 schema extension은 저장하거나 전송하지 않는다.

**선택한 이유**

- LED 표시와 슬롯 내비게이션에는 사용자 콘텐츠가 필요하지 않다.
- private local socket이어도 불필요한 대화와 credential 복사는 노출 범위를 넓힌다.
- strict schema가 Python receiver와 TypeScript publisher 사이의 계약 및 감사 범위를 고정한다.

**검토한 대안**

- 질문 본문이나 답을 status에 표시하는 안은 기능에 불필요하고 privacy 경계를 깨므로 거부했다.
- 알 수 없는 필드를 관대한 방식으로 보존하는 안은 content가 registry로 흘러갈 수 있어 거부했다.
- 임의 error 문자열을 wire로 전달하는 안은 secret이나 사용자 콘텐츠가 섞일 수 있어 거부했다.

**영향과 한계**

- pending request는 내용이 아니라 count와 상태로만 노출된다.
- 512자 identifier, 256 sessions, session당 128 active calls, 512 KiB frame 한도를 적용한다.
- audit sentinel 검증은 bounded evidence이며 모든 미래 오류·로그 경로의 비밀 부재를 보장하지 않는다.

관련 요구사항: [R24](nonfunctional.md#r24) · [R25](nonfunctional.md#r25) · [R28](nonfunctional.md#r28)

근거: [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [REPORT.md](../../experiments/gjc-product-qa/REPORT.md) · [gjc-cli-package-audit.md](../../docs/testing/gjc-cli-package-audit.md) · [gjc-hook-second-audit.md](../../docs/testing/gjc-hook-second-audit.md)


<a id="d08"></a>
## D08 · 로컬 receiver와 registry를 단일 소유

**채택 · 구현 선택**

GJC bridge는 private AF_UNIX endpoint, tracker, atomic registry를 한 receiver가 소유하며 client와 buffer를 제한한다. 두 번째 receiver는 live socket이나 shared registry를 탈취하거나 unlink하지 않고 실패한다.

**선택한 이유**

- 한 serialization boundary에서 producer frame과 control을 처리해야 slot, tombstone, clear 순서를 보존할 수 있다.
- private owner와 mode 검증이 다른 local process의 우발적 충돌과 잘못된 path 정리를 막는다.
- atomic registry는 receiver restart 뒤 slot identity를 복원하는 데 필요하다.

**검토한 대안**

- receiver마다 같은 registry를 독립적으로 쓰는 안은 state corruption과 slot race를 만들 수 있어 거부했다.
- bind 전에 보이는 socket을 무조건 stale로 간주해 unlink하는 안은 live receiver를 파괴할 수 있어 거부했다.
- 무제한 client와 buffer를 허용하는 안은 로컬 장애가 메모리와 종료 시간을 통제하지 못하게 하므로 거부했다.

**영향과 한계**

- socket은 user-owned mode 0600, runtime directory는 0700, registry는 0600이어야 한다.
- malformed client 하나는 격리하고 stop은 receiver thread와 자신의 resource만 종료한다.
- sidecar lock과 path 검사는 협력적 same-user 보호이며 hostile same-UID actor에 대한 완전한 보안 경계는 아니다.

관련 요구사항: [R29](nonfunctional.md#r29) · [R30](nonfunctional.md#r30) · [R34](nonfunctional.md#r34)

근거: [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [transport-audit-report.md](../../docs/testing/transport-audit-report.md) · [gjc-state-audit.md](../../docs/testing/gjc-state-audit.md)


<a id="d09"></a>
## D09 · slot은 연결보다 launch에 고정

**채택 · 사용자 제약·합의**

slot은 live connection이 아니라 launch identity에 안정적으로 배정한다. EOF나 local monotonic 8초 lease 만료는 slot을 유지한 채 unknown으로 만들고, explicit `closed=true`만 자연 해제하며 overflow는 빈 slot이 생긴 뒤에만 승격한다.

**선택한 이유**

- 일시적인 receiver restart와 reconnect가 숫자 키 배정을 바꾸면 사용자가 잘못된 패널로 이동할 수 있다.
- EOF와 lease 만료는 process death의 증거가 아니다.
- overflow가 기존 launch를 밀어내지 않아야 이미 학습한 키 위치가 안정적으로 유지된다.

**검토한 대안**

- disconnect 즉시 slot을 회수하는 안은 살아 있는 publisher의 일시 장애를 새 launch로 오인하므로 거부했다.
- overflow launch가 기존 slot을 선점하는 안은 stable assignment를 깨므로 거부했다.
- receiver wall clock이나 producer timestamp로 lease를 연장하는 안은 clock 조작과 drift에 취약해 거부했다.

**영향과 한계**

- registry 복원 row는 새 complete frame이 오기 전까지 unknown/disconnected로 표시한다.
- 새로운 valid sequence가 reconnect하면 이전 slot을 유지하고 최신 모델 전체를 복구한다.
- 명시적으로 retired된 launch는 늦은 frame으로 부활하지 못한다.

관련 요구사항: [R31](functional.md#r31) · [R32](nonfunctional.md#r32) · [R33](functional.md#r33) · [R35](functional.md#r35)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [REPORT.md](../../experiments/gjc-product-qa/REPORT.md) · [REPORT.md](../../experiments/gjc-product-qa/root-switch/REPORT.md)


<a id="d10"></a>
## D10 · clear는 확인된 dead process에만 허용

**채택 · 사용자 제약·합의**

수동 `clear`는 producer가 disconnected이고 local PID가 OS에서 `ESRCH`로 종료 확인된 경우에만 허용한다. connected, live, lease-expired-only, 권한 거부, invalid 또는 판단 불가능 PID는 force 없이 거부한다.

**선택한 이유**

- unknown 상태만으로 살아 있는 GJC의 slot과 tombstone을 지우면 재연결 state가 손상될 수 있다.
- OS가 확정한 process absence만 bounded reclaim authorization으로 사용할 수 있다.
- control과 frame을 receiver thread에서 직렬화해야 queued reconnect와 clear의 순서를 결정적으로 유지한다.

**검토한 대안**

- lease 만료를 process death로 간주하는 안은 연결 장애와 종료를 혼동해 거부했다.
- `--force`로 ambiguous launch를 삭제하는 안은 보존 계약을 깨므로 제공하지 않는다.
- permission error를 process absence로 취급하는 안은 잘못된 회수를 허용하므로 거부했다.

**영향과 한계**

- 거부 시 launch, slot, registry, tombstone은 그대로이며 후속 heartbeat도 계속 처리한다.
- canonical UUID와 exact response schema를 검증하고 CLI는 거부와 bridge unreachable을 다른 exit로 표시한다.
- 존재하지 않는 launch clear는 상태 변경 없는 no-op이다.

관련 요구사항: [R36](functional.md#r36) · [R37](functional.md#r37) · [R38](functional.md#r38)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-cli-package-audit.md](../../docs/testing/gjc-cli-package-audit.md) · [transport-audit-report.md](../../docs/testing/transport-audit-report.md)


<a id="d11"></a>
## D11 · 사람 요청을 최우선으로 표시

**채택 · 사용자 제약·합의**

launch 집계 우선순위는 `waiting > failed > working > unknown > done > idle`로 고정하고 각각 주황, 빨강, 노랑, 흰색, 초록, 하늘색으로 표시한다. `done`은 관측된 현재 턴의 응답 종료일 뿐 사용자 목표 완료가 아니다.

**선택한 이유**

- 실행 중인 agent가 많아도 답이 필요한 요청 하나를 사용자가 먼저 발견해야 한다.
- 실패와 작업 중, 연결 불명, 턴 종료, 입력 대기를 서로 다른 행동 신호로 구분해야 한다.
- 실험에서 부모 completion 뒤에도 child ask가 남을 수 있어 parent 종료를 전체 완료로 볼 수 없었다.

**검토한 대안**

- agent 수 다수결로 색을 정하는 안은 한 개의 사람 요청을 가릴 수 있어 거부했다.
- `agent_end=completed`만으로 green을 켜는 안은 error, abort, toolUse-only에서도 completed가 관측돼 거부했다.
- 빈 zone key의 하늘색을 idle launch로 해석하는 안은 배정과 renderer 기본값을 혼동하므로 거부했다.

**영향과 한계**

- unresolved ask나 검증된 decision이 하나라도 있으면 다른 working/failed state보다 waiting이 우선한다.
- assigned idle과 vacant key는 같은 색을 사용할 수 있지만 status 의미는 다르다.
- 색상은 상태 요약이며 전체 프로젝트 성공이나 질문 응답 가능 UI를 보증하지 않는다.

관련 요구사항: [R18](functional.md#r18) · [R39](functional.md#r39) · [R40](functional.md#r40)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md)


<a id="d12"></a>
## D12 · 누락과 중단은 unknown으로 보수 처리

**채택 · 검증 후 수정**

연결이 끊기면 이전 waiting·done을 포함한 stale 상태를 unknown으로 표시한다. 연결된 snapshot에서 관찰 한도를 넘으면 incomplete를 드러내고, 이미 확인한 waiting·failed·working의 우선순위는 유지한다. pause·cancel·불충분한 종료 근거를 성공으로 추정하지 않는다.

**선택한 이유**

- native hook은 모든 approval UI와 중첩 event를 제공하지 않으므로 `complete=true`도 GJC 전체 세계의 완전성을 뜻하지 않는다.
- 한도 초과에서 일부 session을 버리고도 done으로 보이면 거짓 성공이 된다.
- 반대로 이미 관측한 사람 요청까지 incomplete가 숨기면 human-priority 목적이 깨진다.

**검토한 대안**

- 관측 누락이 있어도 남은 row로 done/idle을 계산하는 안은 false green 위험 때문에 거부했다.
- incomplete이면 무조건 unknown만 표시하는 안은 확인된 waiting/failed/working을 숨기므로 거부했다.
- disconnect 뒤 stale waiting이나 done 색을 유지하는 안은 현재 liveness를 오도하므로 거부했다.

**영향과 한계**

- status는 `complete=false`와 incomplete coverage를 내용 없이 표시한다.
- 256 session이 모두 사람 요청을 가지면 bounded model은 일부를 잃을 수 있으며 complete=false가 그 한계를 드러낸다.
- unknown은 별도 색을 가지며 성공 또는 idle로 축약하지 않는다.

관련 요구사항: [R28](nonfunctional.md#r28) · [R38](functional.md#r38) · [R39](functional.md#r39)

근거: [gjc-observation-design.md](../../docs/gjc-observation-design.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-coordinator-regressions.md](../../docs/testing/gjc-coordinator-regressions.md) · [gjc-state-audit.md](../../docs/testing/gjc-state-audit.md)


<a id="d13"></a>
## D13 · 질문은 call과 receipt로 상관관계 유지

**채택 · 검증 후 수정**

pending ask는 `(sessionId, toolCallId)` 집합으로 관리하고 decision은 process-local receipt identity로 answer와 결합한다. duplicate/late start, 과거 ask, 재사용 request ID, 다른 tool result는 현재 요청을 열거나 해결하지 못한다.

**선택한 이유**

- `tool_call`과 `tool_execution_start`를 별도 요청으로 세면 동일 ask가 중복 집계된다.
- 동시 ask 중 하나의 답만으로 다른 ask가 끝나지 않는 실제 반례가 확인됐다.
- 문자열 request ID만 비교하면 decision보다 먼저 시작한 ask나 재사용 ID의 과거 답이 미래 decision을 지울 수 있었다.

**검토한 대안**

- request ID 문자열만 같은 answer를 수락하는 안은 시간적 오상관 defect 때문에 폐기했다.
- session completion이나 child shutdown에서 pending을 일괄 제거하는 안은 미해결 사람 요청을 잃으므로 거부했다.
- tool 이름이 다른 result로 call을 종료하는 안은 late/mismatched event에 취약해 거부했다.

**영향과 한계**

- 두 decision의 answer는 독립적으로 소비되고 첫 답이 두 번째 요청을 clear하지 않는다.
- 취소, clarification, collision은 승인으로 취급하지 않으며 불확실하면 pending 또는 incomplete를 유지한다.
- receipt token은 내부에만 존재하고 snapshot이나 registry로 전송하지 않는다.

관련 요구사항: [R17](functional.md#r17) · [R18](functional.md#r18)

근거: [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md) · [gjc-hook-second-audit.md](../../docs/testing/gjc-hook-second-audit.md) · [gjc-coordinator-regressions.md](../../docs/testing/gjc-coordinator-regressions.md) · [qa-report.md](../../experiments/gjc-parent-decisions/evidence/qa-report.md)


<a id="d14"></a>
## D14 · 종료 event와 성공을 분리

**채택 · 검증 후 수정**

green 성공은 검증된 최종 assistant `stop` 또는 검증된 child yield 결과로만 판단한다. assistant error는 failed, aborted는 cancelled, toolUse-only completion과 malformed yield 또는 shutdown-only는 unknown이며 retry, maintenance, pause, queued work는 done이 아니다.

**선택한 이유**

- HTTP·stream 오류, ask 취소, bash 취소에서도 외부 `agent_end.stopReason=completed`가 관측됐다.
- tool 오류 뒤 후속 정상 응답으로 회복되는 경우가 있어 일시 오류를 영구 failed로 고정할 수도 없다.
- child yield 실행에서는 shutdown이 있어도 child agent_end가 없는 경우가 있어 shutdown 자체는 결과가 아니다.

**검토한 대안**

- raw `agent_end=completed`를 성공 oracle로 쓰는 안은 실제 반례 때문에 폐기했다.
- 첫 tool error를 launch의 영구 실패로 유지하는 안은 retry와 최종 assistant 회복을 반영하지 못해 거부했다.
- child shutdown을 성공한 yield로 대신하는 안은 결과 payload 검증을 건너뛰므로 거부했다.

**영향과 한계**

- retry 중에는 일시 terminal failure를 지우고 새 최종 outcome을 기다린다.
- malformed 또는 conflicting yield는 child가 닫혀도 green으로 바뀌지 않는다.
- 실패·취소·late tool result의 event ordering은 명시적으로 reducer에서 처리한다.

관련 요구사항: [R19](functional.md#r19) · [R20](functional.md#r20)

근거: [gjc-observation-design.md](../../docs/gjc-observation-design.md) · [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-hook-second-audit.md](../../docs/testing/gjc-hook-second-audit.md)


<a id="d15"></a>
## D15 · 의사결정 worker는 opt-in read와 yield만 선언

**채택 · 사용자 제약·합의**

설치되는 `keychron-decision-worker`는 사용자가 선택해 쓰는 opt-in agent이며 선언 도구를 `read`, `yield`로 제한한다. 이 제한은 prompt와 agent declaration 계약이지 범용 permission broker나 임의 모델에 대한 강제 보안 경계가 아니다.

**선택한 이유**

- child가 직접 사용자 UI를 소유하지 않고 필요한 결정을 parent로 올리는 단순한 composition이 필요하다.
- read와 yield만 선언하면 결정 조사와 구조화된 handoff라는 역할을 분명히 할 수 있다.
- 실제 fixture에서 child의 direct ask가 `Tool ask not found`로 거부되고 parent-routed 흐름이 동작했다.

**검토한 대안**

- decision worker에 `ask`를 직접 허용하는 안은 parent routing과 실제 응답 위치 계약을 흐리므로 채택하지 않았다.
- prompt 선언이 모든 model, host, tool 권한을 기술적으로 강제한다고 주장하는 안은 근거가 없어 거부했다.
- 모든 worker에 이 agent를 강제하는 안은 opt-in 범위를 넘으므로 채택하지 않았다.

**영향과 한계**

- worker yield는 bare JSON이 아니라 `result.data` 아래 정해진 envelope를 사용한다.
- 실제 model instruction 준수와 별도 실행 환경 권한은 미보장 범위로 문서화한다.
- 이 선택은 GJC 자체의 권한 체계를 변경하지 않는다.

관련 요구사항: [R21](functional.md#r21) · [R45](nonfunctional.md#r45)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [qa-report.md](../../experiments/gjc-parent-decisions/evidence/qa-report.md)


<a id="d16"></a>
## D16 · 결정은 parent가 묻고 실제 child만 재개

**채택 · 사용자 제약·합의**

parent는 child가 `result.data`로 yield한 `status`, `request_id`, `question`, `options`, `checkpoint`를 실제 child ID의 전체 결과에서 읽는다. 같은 request ID로 root `ask`를 수행하고 실제 답이 있을 때만 그 실제 child를 checkpoint와 함께 resume한다.

**선택한 이유**

- 사용자 응답 UI는 Orca 부모 패널에 유지해야 사용자가 답할 수 있는 위치와 상태 표시가 일치한다.
- 실제 child ID와 request ID를 함께 써야 병렬 decision의 답이 서로 섞이지 않는다.
- 두 decision과 악의적 direct-ask fixture에서 독립 correlation과 실제 child resume이 확인됐다.

**검토한 대안**

- child 이름이나 추정 ID로 resume하는 안은 실제 runtime identity를 보장하지 못해 거부했다.
- ask 취소나 빈 응답을 승인으로 간주하는 안은 unresolved request를 잘못 clear하므로 거부했다.
- 질문 화면을 자동 조작하거나 observer overlay Enter를 답변으로 간주하는 안은 실제 UI 의미가 달라 거부했다.

**영향과 한계**

- 첫 answer는 matching child만 해결하며 나머지 decision은 waiting으로 남는다.
- checkpoint와 answer는 worker continuation에 명시적으로 전달하지만 wire와 registry에는 넣지 않는다.
- fixture 성공은 tool composition 증거이며 실제 model이 항상 이 순서를 따른다는 보장은 아니다.

관련 요구사항: [R18](functional.md#r18) · [R21](functional.md#r21) · [R22](functional.md#r22)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [qa-report.md](../../experiments/gjc-parent-decisions/evidence/qa-report.md) · [REPORT.md](../../experiments/gjc-product-qa/REPORT.md)


<a id="d17"></a>
## D17 · 재시작 뒤에는 successor로 명시적 인계

**채택 · 사용자 제약·합의**

GJC process restart로 이전 in-memory child를 재개할 수 없으면, checkpoint와 실제 answer를 명시적으로 전달한 별도 successor child를 시작한다. 원래 child를 재개했다고 주장하지 않는다. 검증 실험에서는 이전 child의 native not_found 응답으로 이 경계를 확인했다.

**선택한 이유**

- GJC child identity와 resume 가능성은 process memory 수명에 묶여 있다.
- 없는 predecessor를 재개했다고 기록하면 사용자 결정의 소비 주체와 실행 이력이 거짓이 된다.
- 실제 GJC 0.16.4 restart 실험에서 launch B가 predecessor를 `not_found`로 거부하고 distinct successor가 continuation을 완료했다.

**검토한 대안**

- process restart 뒤 원래 child가 자동 복구됐다고 간주하는 안은 native runtime 결과와 달라 거부했다.
- answer와 checkpoint를 제품이 자동 영구 저장한다고 주장하는 안은 구현되지 않아 거부했다.
- stale resume transport 성공을 semantic resume 성공으로 보는 안은 `not_found` receipt를 놓치므로 거부했다.

**영향과 한계**

- successor는 predecessor와 다른 actual child ID를 가져야 하며 결과에도 successor임을 명시한다.
- checkpoint와 answer의 process 간 전달은 호출자가 수행하는 명시적 composition이다.
- 실험은 deterministic fixture 흐름을 증명하지만 automatic durable recovery나 real-model 준수는 보장하지 않는다.

관련 요구사항: [R23](functional.md#r23)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [REPORT.md](../../experiments/gjc-successor-audit/REPORT.md) · [gjc-second-audit.md](../../docs/testing/gjc-second-audit.md)


<a id="d18"></a>
## D18 · 한 배포판에서 Python 패키지 경계 분리

**채택 · 구현 선택**

배포판은 `orca-keychron` 하나를 유지하되 기존 공통 runtime은 `orca_keychron`, GJC 전용 protocol, tracker, source, installer, CLI는 `orca_keychron_gjc`에 둔다. 의존 방향은 GJC 패키지에서 core 패키지로만 향한다.

**선택한 이유**

- 검증된 HID, renderer, input, Orca navigation을 복제하지 않고 재사용해야 두 mode의 동작이 갈라지지 않는다.
- GJC protocol과 설치 코드를 core가 import하지 않아 기존 Orca mode의 경계를 보존한다.
- 한 wheel에 두 entrypoint와 assets를 포함하면 설치·버전·release provenance를 함께 검증할 수 있다.

**검토한 대안**

- GJC를 별도 배포판으로 분리하는 안은 공통 하드웨어 코드 중복과 release 조합을 늘려 채택하지 않았다.
- GJC 패키지에 HID와 navigation을 복사하는 안은 유지보수 분기를 만들므로 거부했다.
- core가 GJC protocol을 import하는 양방향 결합은 기존 Orca mode에 GJC 의존을 넣으므로 거부했다.

**영향과 한계**

- CLI entrypoint는 `orca-keychron`과 `orca-keychron-gjc` 두 개이며 Python 3.9 이상을 유지한다.
- built wheel이 두 패키지와 TypeScript/Markdown assets를 실제 포함하는지 checkout 밖에서 검증한다.
- GJC launch ID는 공통 display identity로 전달하되 Orca worktree ID로 바꾸어 저장하지 않는다.

관련 요구사항: [R07](nonfunctional.md#r07) · [R09](functional.md#r09) · [R11](nonfunctional.md#r11) · [R41](nonfunctional.md#r41) · [R43](functional.md#r43)

근거: [gjc-package-layout.md](../../docs/gjc-package-layout.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-validation.md](../../docs/gjc-validation.md) · [gjc-cli-package-audit.md](../../docs/testing/gjc-cli-package-audit.md)


<a id="d19"></a>
## D19 · GJC 전용 CLI와 저장된 socket 계약

**채택 · 구현 선택**

`orca-keychron-gjc`는 `setup`, `run`, `serve`, `status`, `clear`, `install`, `uninstall`, `doctor`, `autostart`의 아홉 명령을 제공한다. setup이 저장한 absolute socket을 explicit override가 없을 때 install, run, serve, status, doctor가 공유하며 serve는 receiver와 tracker만 실행한다.

**선택한 이유**

- hook loader와 receiver가 같은 endpoint를 사용해야 native publisher가 연결된다.
- HID 없는 serve를 분리하면 상태 수신·진단을 hardware나 global service mutation 없이 실행할 수 있다.
- 기존 Orca mode 설정과 분리된 private GJC runtime 경로가 mode 간 오염을 막는다.

**검토한 대안**

- 명령마다 서로 다른 implicit socket을 계산하는 안은 loader와 receiver mismatch를 만들 수 있어 거부했다.
- serve가 HID나 외부 Orca 명령을 시작하는 안은 receiver-only 계약을 깨므로 거부했다.
- socket 변경 뒤 기존 loader를 계속 쓰는 안은 endpoint가 어긋나므로 재설치를 요구한다.

**영향과 한계**

- config는 valid/private file이어야 하며 custom socket은 setup 후 install 순서로 반영한다.
- status는 live receiver 실패 시 registry를 offline/unknown으로 명시하고 corrupt registry를 정상 empty로 보이지 않는다.
- doctor는 GJC 버전, config, hook, receiver, autostart를 서로 다른 진단 차원으로 표시한다.

관련 요구사항: [R07](nonfunctional.md#r07) · [R08](functional.md#r08) · [R09](functional.md#r09) · [R10](functional.md#r10) · [R38](functional.md#r38)

근거: [gjc-guide.md](../../docs/gjc-guide.md) · [gjc-package-layout.md](../../docs/gjc-package-layout.md) · [gjc-cli-package-audit.md](../../docs/testing/gjc-cli-package-audit.md)


<a id="d20"></a>
## D20 · hook 설치는 소유권과 immutable release로 제한

**채택 · 구현 선택**

user root는 explicit agent dir, environment, default 순으로 선택하고 project root는 `<project>/.gjc`로 고정한다. installer는 digest manifest로 증명된 loader, worker, immutable release만 transaction journal을 통해 설치·교체·삭제하며 conflict, user edit, unsafe path는 보존하고 거부한다.

**선택한 이유**

- GJC native discovery가 기대하는 user/project 경로를 따르면서 제품이 만든 파일만 관리해야 한다.
- immutable digest release와 loader 분리는 upgrade 중 자산 identity와 rollback 대상을 명확히 한다.
- 중단과 fsync/replace 실패에서도 기존 유효 설치를 복구할 수 있어야 한다.

**검토한 대안**

- GJC root 전체를 제품 소유로 간주해 덮어쓰거나 mode를 바꾸는 안은 사용자 파일을 훼손할 수 있어 거부했다.
- manifest 확인 없이 이름만 같은 파일을 삭제하는 안은 unowned content를 지울 수 있어 거부했다.
- dry-run에서도 실제 mutation이나 GJC 버전 설치를 요구하는 안은 안전한 계획 확인을 방해해 거부했다.

**영향과 한계**

- 새 관리 directory는 0700, file은 0600이며 loader config에는 socket path만 포함한다.
- uninstall은 hook 소유 파일만 제거하고 runtime config와 service를 자동 삭제하지 않는다.
- FIFO, symlink, malformed metadata, modified owned file과 inspection ambiguity는 fail closed로 처리한다.

관련 요구사항: [R02](functional.md#r02) · [R03](functional.md#r03) · [R04](functional.md#r04) · [R05](nonfunctional.md#r05) · [R06](functional.md#r06)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-owned-boundaries-second-audit.md](../../docs/testing/gjc-owned-boundaries-second-audit.md)


<a id="d21"></a>
## D21 · 두 mode는 cooperative HID와 별도 service를 사용

**채택 · 구현 선택**

Orca mode와 GJC mode는 같은 cooperative device lock을 획득한 뒤에만 Keychron HID를 열고, GJC login service는 별도 namespace를 사용한다. GJC autostart는 현재 또는 legacy Orca service가 설치·로드됐거나 검사 불명일 때 거부하며 mode 전환은 기존 foreground와 LaunchAgent를 먼저 종료·제거한다.

**선택한 이유**

- 동일 제품의 두 renderer가 한 HID device에 동시에 쓰는 우발적 충돌을 막아야 한다.
- service namespace와 ownership을 분리해야 기존 Orca mode를 덮어쓰거나 bootout하지 않는다.
- base Orca installer는 GJC를 대칭 검사하지 않으므로 사용자 전환 절차가 비대칭 구현을 보완해야 한다.

**검토한 대안**

- 두 mode를 동시에 실행하는 안은 HID frame 경쟁을 일으키므로 지원하지 않는다.
- GJC installer가 기존 Orca service를 자동 제거하는 안은 다른 mode의 사용자 상태를 변경하므로 거부했다.
- cooperative lock을 OS 전체 HID 독점이나 Keychron Launcher 차단으로 표현하는 안은 보장 범위를 넘으므로 거부했다.

**영향과 한계**

- 정상 종료와 SIGKILL 뒤 lock은 다음 협력 process가 획득할 수 있어야 한다.
- short HID write와 runtime failure는 실패로 처리하고 조명 복구, source stop, device close를 수행한다.
- 실제 login service activation은 수행되지 않았으며 launchctl 경계는 stateful fake와 파일 보존으로 검증됐다.

관련 요구사항: [R12](functional.md#r12) · [R41](nonfunctional.md#r41) · [R42](nonfunctional.md#r42)

근거: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [gjc-owned-boundaries-second-audit.md](../../docs/testing/gjc-owned-boundaries-second-audit.md) · [gjc-shared-runtime-second-audit.md](../../docs/testing/gjc-shared-runtime-second-audit.md)


<a id="d22"></a>
## D22 · 숫자 키는 Orca 부모 패널로 이동

**채택 · 사용자 제약·합의**

Orca가 frontmost일 때 `Option`과 표시 키 `1`부터 `0`, `-`, `=`를 누르면 즉시 해당 launch의 Orca 부모 pane으로 이동한다. child transcript나 질문 화면을 자동으로 열지 않으며 stale 또는 재배정된 target에는 dispatch하지 않는다.

**선택한 이유**

- 실제 child 질문을 observer overlay에서 직접 답하는 경로가 확인되지 않았고 Enter는 펼치기 동작이었다.
- launch slot의 안정된 의미는 사용자에게 돌아갈 부모 작업 pane이어야 한다.
- 기존 Orca input 동작과 일반 앱 입력을 보존해야 한다.

**검토한 대안**

- child session마다 키를 재배정하는 안은 launch 슬롯 계약을 깨므로 거부했다.
- Ctrl+S나 observer overlay를 자동 주입해 질문을 여는 안은 현재 질문 UI를 가리거나 답변 가능성을 오인하게 해 거부했다.
- 길게 누르기 또는 일반 숫자 단독 입력으로 설명하는 안은 실제 Option 조합과 달라 정정했다.

**영향과 한계**

- 다른 앱이 frontmost이거나 Shift, Control, Command가 함께 눌리면 단축키를 가로채지 않는다.
- 같은 키의 재실행은 key release 뒤 허용하고 release 전에 바뀐 slot target은 취소한다.
- 실제 navigator panel switch는 검증됐지만 physical Option key 입력 전체 chain은 미실행이다.

관련 요구사항: [R43](functional.md#r43) · [R44](functional.md#r44)

근거: [gjc-observation-design.md](../../docs/gjc-observation-design.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md) · [gjc-shared-runtime-second-audit.md](../../docs/testing/gjc-shared-runtime-second-audit.md)


<a id="d23"></a>
## D23 · 모든 승인 UI와 모델 강제 보장은 제외

**제외 · 사용자 제약·합의**

제품이 모든 GJC approval, permission, confirm, input UI를 관찰하고 모든 child 질문에 직접 답하게 하거나, 선언된 `read`와 `yield` 권한을 모든 model과 host에서 강제한다는 보장은 제품 범위로 채택하지 않는다.

**선택한 이유**

- AskTool, notification, protocol permission, child local gate, extension UI는 서로 다른 응답 경로를 가진다.
- 실제 extension confirm/input은 native 상태 hook에 나타나지 않았고 child observer에서 답변 경로도 확보되지 않았다.
- agent prompt와 선언 도구는 model instruction이지 실행 환경 전체의 security enforcement가 아니다.

**검토한 대안**

- 새 answer provider를 등록해 응답 소유권을 바꾸는 안은 표시 기능이 사용자 응답 경로를 변경하므로 거부했다.
- `action_unavailable`이나 내부 paused를 요청 부재로 해석하는 안은 관찰 client 능력과 실제 요청 존재를 혼동해 거부했다.
- native hook 성공을 보편적 UI 관찰과 model 준수 증거로 확대하는 안은 실험 범위를 넘어 거부했다.

**영향과 한계**

- waiting은 관측된 ask 또는 검증된 decision handoff이며 실제 응답 UI 접근 가능성까지 뜻하지 않는다.
- 지원되지 않은 UI나 model behavior는 unknown 또는 문서화된 제한으로 남긴다.
- 범용 approval 통합이나 permission broker는 새 요구와 별도 설계 없이는 포함하지 않는다.

관련 요구사항: [R21](functional.md#r21) · [R22](functional.md#r22) · [R25](nonfunctional.md#r25) · [R45](nonfunctional.md#r45)

근거: [gjc-observation-design.md](../../docs/gjc-observation-design.md) · [gjc-hook-experiment-results.md](../../docs/gjc-hook-experiment-results.md) · [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-guide.md](../../docs/gjc-guide.md)


<a id="d24"></a>
## D24 · 검증 층을 분리하고 oracle을 같은 시점에 묶음

**채택 · 검증 후 수정**

source/unit, socket·subprocess integration, built package, 실제 GJC fixture runtime, firmware ACK, navigator, physical input, optical color, real model 검증을 서로 다른 증거 층으로 기록한다. 상태와 색상 주장은 같은 producer, launch, sequence의 exact snapshot에 묶거나 replay라고 명시한다.

**선택한 이유**

- 테스트 파일 이름이나 mock event 통과만으로 실제 GJC 실행 또는 사용자-visible E2E를 증명할 수 없다.
- 과거 12-agent waiting frame과 나중 orange status를 launch ID만으로 결합한 oracle이 false positive를 허용했다.
- 실제 frame을 installed parser, tracker, renderer에 replay하면 identity, count, pending, state와 color를 한 관측 단위로 검증할 수 있다.

**검토한 대안**

- 서로 다른 시점의 frame과 color를 같은 launch ID만으로 결합하는 oracle은 temporal mismatch 때문에 폐기했다.
- synthetic helper test를 실제 GJC E2E로 부르는 안은 실행 경계를 오도하므로 거부했다.
- firmware ACK를 눈으로 본 색상이나 physical key input 성공으로 표현하는 안은 증거가 없어 거부했다.

**영향과 한계**

- actual GJC fixture run은 unmodified runtime과 product hook composition을 증명하지만 real model 정확도를 증명하지 않는다.
- exact-snapshot installed-product replay는 renderer oracle이며 contemporaneous optical observation이 아니다.
- 과거 validation 수치와 현재 frozen gate는 별도 provenance로 유지한다.

관련 요구사항: [R39](functional.md#r39) · [R40](functional.md#r40) · [R45](nonfunctional.md#r45)

근거: [gjc-second-audit.md](../../docs/testing/gjc-second-audit.md) · [FINAL_REPORT.md](../../experiments/gjc-e2e-audit/FINAL_REPORT.md) · [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md) · [gjc-astra-second-review.md](../../docs/testing/gjc-astra-second-review.md)


<a id="d25"></a>
## D25 · 물리 입력과 real model 검증은 별도 과제로 유지

**보류 · 검증 후 수정**

실제 Option 키 입력부터 panel 이동까지의 물리 chain, LED 육안 색상, real provider/model 지침 준수, login service 활성화, 실제 Linux runner 검증은 현재 완료 주장에 포함하지 않고 각각의 별도 실행 전까지 미검증으로 유지한다.

**선택한 이유**

- 현재 실제 GJC 검증은 deterministic loopback fixture provider를 사용했다.
- Q65 Max 검증은 firmware ACK와 조명 복구를 확인했지만 사람이 색을 눈으로 확인하거나 physical key를 누르지 않았다.
- launchctl과 Linux 경계는 simulated/static evidence가 있으며 실제 전역 service와 Ubuntu runtime은 실행하지 않았다.

**검토한 대안**

- Q65 enumeration이나 firmware ACK만으로 physical user E2E를 완료 처리하는 안은 거부했다.
- fixture provider의 compliant response로 모든 real model의 instruction 준수를 보장하는 안은 거부했다.
- macOS 테스트와 workflow 설정만으로 actual Linux CI runtime을 통과했다고 표현하는 안은 거부했다.

**영향과 한계**

- 현재 지원 주장은 GJC 0.16.4 software/package와 bounded actual-runtime composition에 한정한다.
- hardware 기록은 firmware response와 navigator 증거를 physical input·optical 검증과 분리한다.
- 향후 각 deferred boundary를 실행하면 기존 증거를 덮어쓰지 말고 새 provenance로 추가해야 한다.

관련 요구사항: [R12](functional.md#r12) · [R40](functional.md#r40) · [R42](nonfunctional.md#r42) · [R44](functional.md#r44) · [R45](nonfunctional.md#r45)

근거: [gjc-validation.md](../../docs/gjc-validation.md) · [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md) · [FINAL_REPORT.md](../../experiments/gjc-e2e-audit/FINAL_REPORT.md) · [gjc-second-audit.md](../../docs/testing/gjc-second-audit.md)
