# 가재코드 상태 관찰과 Keychron 표시 설계 재검토

2026-09-06. 코드 근거와 신규 제안을 구분한 실험 전 조사 기록. 아래 버전·미실행 문구는 조사 당시 기준이다.

> 후속 실험 완료: 설치된 **GJC 0.16.4**에서 native hook push, 실제 질문·취소·자식·손자·재시도·일시정지·재개를 검증했다. parentSession 부재, 확장 UI 누락, child 질문 응답 경로와 스트림 복구 한계도 확인했다. 현재 판단은 [23개 시나리오 실험 결과](gjc-hook-experiment-results.md)를 기준으로 한다. 제품 구현과 물리 키보드 검증은 아직 수행하지 않았다.

> 최신 제약과 정정: 대표님은 GJC 소스 변경 및 별도 PR을 제외했다. 아래 core observer 권고는 채택하지 않는다. 추가 조사에서 네이티브 `.gjc/hooks`는 일반 filesystem extension과 달리 실제 로딩된다는 점을 확인했다. `sdk/session.ts:3190-3200,3460` → `extensibility/hooks/loader.ts` 경로이며 HookAPI는 agent_start/end와 tool_call/result를 제공한다. 따라서 GJC 무수정 상태 송신 실험이 가능하다. 다만 HookAPI에는 ExtensionAPI의 events bus가 없고, 모든 질문·권한·중첩 자식/job의 완전한 관찰은 아직 보장할 수 없다. 우선 이 훅으로 기본 lifecycle과 AskTool 전후 상태를 로컬 소켓으로 전송하고 실제 누락 범위를 검증한다. Hook의 도구 호출은 실제 질문 UI 대기의 완전한 대체 신호가 아니며, 도구가 차단·취소되는 경로도 처리해야 한다.

## 조사 범위

대표님이 지정한 Orca 터미널 `term_fbb2115a-a9b8-4971-90c0-34ac40e0d69b`의 최근 출력을 읽고, 해당 터미널이 작성한 `/tmp/gjc-keychron-analysis-20260906.md`를 검토했다. 터미널에 입력하지 않았다.

상세 소스 기준은 `f50b17a7fa9faab5935cbf2c358794597b1bd760`이며 package 버전은 0.16.4다. 로컬 `gjc --version`은 0.16.0이다. 버전 차이를 확인하기 위해 upstream v0.16.0 태그(a980e25ad6e519f86ca13da7115020aa708bdff7)의 main.ts, sdk/session.ts, sdk/bus/index.ts, sdk/host/session-runtime.ts, extensions/loader.ts를 별도로 받았다. 이 중 파일 확장 자동 로딩이 차단된 경로를 양쪽에서 대조했다. 아래 모든 상세 경로를 설치 바이너리에서 실행 검증한 것은 아니다.

## 이전 제안에서 바로잡을 점

1. `.gjc`에 확장 파일을 설치하면 일반 gjc가 로딩한다는 가정은 틀렸다. main은 additionalExtensionPaths를 비우고 세션 factory는 filesystem extension discovery를 무시한다. 명시적 factory/preloaded 경로는 별개로 남아 있다. v0.16.0 소스에서도 같은 제한을 확인했다.
2. SDK 연결만으로 모든 사람 호출과 자식 상태를 받는다는 가정은 성립하지 않는다. 일반 TUI의 로컬 질문, 알림 활성화된 질문, protocol UI/permission 요청, 자식 로컬 workflow gate는 전달 경로가 다르다.
3. agent_end 또는 그 stopReason=completed만으로 성공을 판단하면 안 된다. provider 메시지의 error/aborted 경로에서도 completed 종료 이벤트를 만들 수 있다.
4. root task eventBus 하나를 구독한다고 모든 중첩 자식과 background job 상태를 얻지는 못한다.
5. 현재 Keychron 입력은 macOS에서 Orca가 전면일 때 Option+숫자로 동작하며 hold 시간은 설정값이다. 일반 숫자 단독 길게 누르기를 기존 기능처럼 설명한 것은 부정확했다. 기본 입력 조합 변경은 별도 제품 결정이다.

근거: [v0.16.0 main](https://github.com/Yeachan-Heo/gajae-code/blob/a980e25ad6e519f86ca13da7115020aa708bdff7/packages/coding-agent/src/main.ts#L1284), [v0.16.0 factory](https://github.com/Yeachan-Heo/gajae-code/blob/a980e25ad6e519f86ca13da7115020aa708bdff7/packages/coding-agent/src/sdk/session.ts#L3431), [오류 종료 경로](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/agent/src/agent-loop.ts#L4196), 로컬 src/orca_keychron/digit_hold.py.

## 실제 사람 호출 경로

| 발생 위치 | 코드에서 확인한 경로 | 수동 SDK 관찰만으로 완전한가 |
|---|---|---|
| 일반 TUI AskTool, answer source 없음 | 로컬 UI selector/editor | 아니오 |
| 알림 runtime이 활성화된 root AskTool | 로컬 UI와 원격 응답 경합, presentation 생성 | 조건부 |
| protocol UI/permission source 등록됨 | 해당 provider에 reverse request | 알림 broadcast와 별개 |
| 자식 AskTool | headless 자식의 local workflow gate 경로 가능 | root SDK에 자동 전달되지 않음 |
| 확장 UI select/confirm/input/custom | TUI controller 호출 | 일반적인 사람 호출 broadcast 확인 안 됨 |

AskTool은 로컬 답변 시 원격 대기를 취소하고 원격 답변 시 로컬 selector를 취소한다. 관찰기는 이 응답 소유권을 바꾸지 않아야 한다. 새 answer provider를 등록하면 응답 경로 자체를 바꾸므로 표시용 해결책으로 사용하지 않는다.

자식의 local gate가 있다는 사실만으로 대표님이 부모 터미널에서 바로 답할 수 있다고 표시해서도 안 된다. 질문 발생 actor와 실제 응답 대상, 현재 답변 가능 여부를 별도 보관한다. 내부 pending/paused만으로 사람 호출을 추정하지 않는다. `action_unavailable`은 관찰 클라이언트가 표현 기능을 갖추지 못했다는 뜻일 수 있어 요청 부재로 취급하지 않는다.

근거: [AskTool 분기](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/tools/ask.ts#L859), [알림 활성화](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/sdk/bus/index.ts#L7866), [child local publication](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/sdk/session.ts#L4509), [child gate store](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/session/agent-session.ts#L11311), [protocol 의미](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/crates/gjc-sdk/src/protocol.rs).

## 자식·job 관찰의 범위

확장 API의 events.on은 실제 EventBus를 구독한다. 다만 bus 자체에는 snapshot/replay/seq가 없다. 직접 자식의 lifecycle/progress/raw AgentEvent는 부모 bus에 전달되지만, 자식은 자신의 bus를 만들 수 있으므로 손자 이벤트 전체의 재귀 전달은 보장되지 않는다.

AgentRegistry에는 parentId와 list/onChange가 있고 AsyncJobManager에는 owner 정보와 onChange가 있다. 공개 확장 context의 getJobs는 owner별 제한된 snapshot이며 onJobFold는 모든 job 변경을 뜻하지 않는다. 전역 singleton을 import해서 현재 세션의 manager라고 가정하면 다른 root 세션과 섞일 수 있다.

따라서 현재 요구에 맞는 최소 신규 관찰 계약은 `getSessionFamilySnapshot()`과 `observeSessionFamily(listener)`다. 이름은 제안이다. root별 세션·actor 계층, owner별 jobs, 실제 사람 요청, 실행 결과를 같은 문맥에서 내보낸다.

근거: [bus](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/utils/event-bus.ts#L6), [확장 API](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/extensibility/extensions/types.ts#L1428), [child 생성](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/task/executor.ts#L1999), [owner별 jobs](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/session/agent-session.ts#L5671).

## 권장 통합 구조 — 신규 설계

```text
Orca 터미널 안의 GJC
  root lifecycle + 자식/owner jobs + 사람 요청 lifecycle
  → 관찰 전용 상태 저장소
  → 초기 snapshot + 변경 이벤트 (로컬 socket)

Keychron 프로그램
  → root 세션에 고정 키 배정
  → 상태 저장 및 우선순위 집계
  → RGB 출력
  → 기존 Orca terminal 이동
```

가재코드가 업무 의미와 계층을 정리하고, Keychron은 슬롯/색상/이동을 담당한다. `.gjc`는 필요하다면 연결 정보·복구 정보의 위치로 사용한다. 최신 파일 하나를 여러 번 읽는 방식으로 순간적인 상태 전이를 복원하려 하지 않는다. 기존 SDK는 검증된 일부 입력 경로로 활용할 수 있지만 전체 관찰 보장을 대신하지 않는다.

Orca 환경변수를 상속받았다는 이유만으로 모든 중첩 gjc를 새 root로 등록하지 않는다. GJC의 기존 Herdr 연동에도 자식 프로세스가 부모 pane의 표시 소유권을 빼앗지 않도록 owner marker를 검사하는 선례가 있다. root/parent identity와 실행 incarnation으로 실제 사용자 세션을 구분해야 한다. [Herdr 소유권 처리](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/utils/herdr-pane.ts#L248).

GJC 내부 관찰기가 초기 상태와 pending 목록을 유지한다. 구독과 snapshot에는 같은 실행 epoch 및 순번 경계가 필요하다. 느린 수신기에는 유한 큐를 적용하고 overflow 시 재동기화한다. 토큰 스트림이나 전체 도구 출력은 LED에 필요하지 않다. heartbeat는 연결 생존 확인에만 사용하고 업무 상태를 반복 조회하지 않는다.

## 표시 정책 — 신규 제안

한 키는 독립 root 세션과 해당 요청에 소속된 자식 작업을 뜻한다. 프로젝트나 에이전트 수의 다수결로 결정하지 않는다. 원천 상태를 색 enum 하나로 축약해 저장하지 않는다.

| 실제 상황 | 대표 표시 | 상세에 남길 내용 |
|---|---|---|
| 실행 10 + 답변 가능한 미해결 질문 1 | 주황 | 질문을 먼저, 실행 수를 다음에 |
| 답변 가능한 질문 + 복구되지 않은 실패 | 주황 | 둘 다 보존; 마지막 질문 해소 후 실패 재평가 |
| 자식 오류, 부모가 재시도·대체 실행 중 | 노랑 | 내부 오류 및 복구 중 |
| root 정상 결과 확정 + 해당 요청의 필수 작업 없음 | 초록 | 이번 요청 결과; 전체 프로젝트 목표 완료와 구분 |
| 중단/일시정지/관찰 불명 | 성공 초록 금지 | 중단·일시정지·연결 불명을 구분 |

주황색은 실제 답변 가능한 사람 호출이 있을 때 적용한다. 호출은 있으나 응답 경로가 없으면 조치가 필요한 막힘으로 별도 분류하고, 접근 가능한 응답 UI가 있다는 인상을 주지 않는다. 이 상황의 구체적인 LED 표현은 확정 전이다.

미해결 질문은 ID별로 추적하며 질문 해소/취소/만료 사실만으로 제거한다. 터미널 이동이나 상세 목록 열기는 질문 해결이 아니다. 새 작업 이벤트가 기존 질문을 덮지 않는다. 실패 기록은 자동 복구 여부와 현재 요청에 대한 영향을 확인하며 모든 과거 오류를 영구 빨강으로 만들지 않는다.

완료는 raw turn_end/agent_end 이름만으로 판단하지 않는다. assistant 결과 오류·취소, maintenance/자동 후속 실행, 현재 요청에 소속된 미완료 jobs를 함께 확인한다. 서로 독립적인 지속 background 작업을 완료 조건에 무조건 포함하지 않는다. 소유권/현재 요청 소속을 판단할 근거가 부족하면 전체 완료라고 단정하지 않는다.

## 상세 확인 UX — 기존 기능과 제안 구분

GJC에는 app.session.observe(기본 Ctrl+S)의 하위 세션 관찰 overlay와 app.jobs.open(기본 Alt+J)이 있다. 관찰 overlay는 상태 registry와 transcript를 보여주는 기능이며 모든 질문에 직접 답하는 통합 화면은 아니다. SessionObserverRegistry의 단순 상태 투영은 paused 등을 완전히 반영하지 않는다.

기본 제안은 키 입력으로 Orca 터미널에 이동하고, 질문이 있으면 기존 질문 UI를 유지하는 것이다. 상세가 필요할 때 GJC 관찰 화면을 연다. 키보드의 숫자 슬롯을 자식용으로 일시 재배정하지 않는다. 터미널 포커스 성공과 자식 transcript 열기, 특정 질문의 응답 화면 열기는 서로 다른 동작으로 구현·검증한다. 자동으로 Ctrl+S를 주입해 현재 질문을 가리는 방식은 피한다.

근거: [기본 키](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/config/keybindings.ts#L200), [overlay 진입](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/modes/interactive-mode.ts#L2309), [관찰 상태 투영](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/modes/session-observer-registry.ts#L5).

## 구현 범위 선택

| 선택 | 비용과 효과 |
|---|---|
| GJC 무수정으로 읽을 수 있는 SDK/상태 파일만 활용 | 착수 범위는 작으나 질문·자식·성공 판정의 누락이 남는다. 완전한 사람 호출 우선 표시를 보장할 수 없다. |
| GJC에 관찰 전용 API/내장 exporter 추가 | GJC 쪽 변경·버전 호환·유지보수가 필요하다. 일반 gjc 사용 흐름과 응답 소유권을 유지하면서 일관된 상태 관찰이 가능하도록 설계할 수 있다. 권고안이다. |

명시적 SDK factory를 넣는 별도 launcher는 실험 경로로 가능하지만, 일반 gjc를 그대로 실행한다는 경험과 다르고 중첩 자식/모든 jobs/질문 관찰 문제도 자동 해결하지 않는다.

## 다음 검증 — 미실행

1. 초기 snapshot 및 구독 경계를 갖는 최소 관찰 API를 별도 실험에서 연결한다. 실제 모델 호출 없이 제어 가능한 세션/질문 이벤트로 먼저 확인한다.
2. 로컬 root 질문, 원격에서 답한 질문, 자식 local gate, permission 거절을 각각 재현해 request lifecycle과 응답 대상이 일치하는지 확인한다.
3. 자식·손자·background job을 구분하고 재시도/일시정지/취소/자동 후속 실행 시 잘못된 초록이 없는지 확인한다.
4. 재연결·순번 누락·producer 재시작 시 초기 상태를 복구하며 오래된 완료가 현재 실행을 덮지 않는지 확인한다.
5. 그 다음 Orca 실제 pane 매핑과 물리 Keychron LED/입력을 확인한다. 코드 조사 및 모의 이벤트 검증과 물리 E2E를 별도로 보고한다.
