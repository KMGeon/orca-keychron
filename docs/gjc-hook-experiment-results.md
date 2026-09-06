# GJC 0.16.4 상태 훅 실험 결과

실험일: 2026-09-06 KST. **GJC 코어 수정·업스트림 PR 없이 native hook에서 상태를 push하는 경로는 실제 동작했다.** 메인 질문, 자식·손자 세션, 재시도, 일시정지·재개까지 관측했다. 다만 모든 사람 요청을 감지하거나 키를 눌러 모든 자식 질문에 답하는 기능까지 검증된 것은 아니다.

실행 대상은 설치된 `gjc/0.16.4`다. 소스 대조 기준은 [f50b17a의 package.json](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/package.json)과 같은 commit의 구현이다. 바이너리와 해당 commit의 빌드 동일성까지 증명한 것은 아니다.

## 실험 방법과 결과 읽는 법

- 실제 설치된 GJC를 실행하고, 외부 모델 대신 loopback의 결정적 모의 모델로 도구 호출·실패·대기를 만들었다. GJC 자체와 native hook 실행은 실제다.
- 질문·취소·세션 전환은 별도 Orca 터미널에서 실제 TUI로 수행했다. 화면은 Orca `terminal read --screen`으로 보존했다.
- 정상 스트림은 파일 JSONL과 TCP 수신 event ID를 비교했다. 별도로 수신기 손실·재접속·SIGKILL을 실험했다.
- 상태 집계 정책과 exporter 방어 처리는 별도 자동 검증으로 구분했다. **27개 테스트, 83개 assertion 통과**: exporter mock 12개, 상태 정책 15개.
- 이 보고서의 범위는 아래 23개 시나리오다. 실제 Keychron HID·LED 점등·키로 자식 질문에 답하기와 실제 외부 모델 제공자의 모든 오류는 포함하지 않는다.

`확인`은 해당 관측이 재현됐다는 뜻이다. 원래 기대가 깨진 반례를 발견한 경우도 포함하며, 제품 기능 전체가 통과했다는 뜻은 아니다. `부분`과 `미실행`은 그대로 남겼다.

## 23개 시나리오

증거 경로는 [`experiments/gjc-hooks/evidence/`](../experiments/gjc-hooks/evidence/) 기준이다.

| # | 시나리오 | 결과 | 관측과 증거 |
|---|---|---|---|
| 1 | 일반 최종 응답 | 확인 | documented lifecycle 7/7 전송. `cases/success_v2/` |
| 2 | read·bash 실행 | 확인 | 도구 전후 이벤트. runtime 이벤트를 추가한 read는 18/18. named `observer.ts`에서는 `tool_call` 누락, literal `*.ts`에서 수신. `read_doc`, `read_runtime`, `read_named`, `bash` |
| 3 | 메인 ask 대기→응답 | 확인 | 실제 질문 UI 동안 start만 있고, Enter 후 result/end. `screens/ask-screen.txt`, `ask-answered.txt`, `cases/tui_v2/` |
| 4 | 한 ask 안 질문 두 개 | 확인 | 첫 응답 후 두 번째 질문 UI 유지, 도구 종료 없음. 모두 답한 뒤 종료. `screens/ask-two-first-answer.txt`, `ask-two-all-answered.txt` |
| 5 | ask 두 개 동시 호출 | 반례 확인 | 서로 다른 toolCallId 두 개가 시작. 하나만 답하면 다른 호출이 미해결. 이 실행에서는 두 번째 선택 UI가 남지 않고 일반 입력창으로 돌아가 Escape로 종료했다. `screens/ask-parallel-unresolved.txt`, `cases/tui_v2/` seq40–51 |
| 6 | 질문 취소 | 반례 확인 | 실제 Escape 후 tool isError=true. 외부 `agent_end`는 `completed`, assistant는 `toolUse`만 남는다. 취소를 성공으로 표시하면 안 됨. `screens/ask-cancel-after.txt`, `tui_v2` seq58–64 |
| 7 | 도구 오류 후 복구 | 확인 | 오류 도구 결과 이후 후속 실행·정상 최종 응답. 도구 오류 한 번을 root 최종 실패로 고정할 수 없음. `tool_failure`, `tool_retry` |
| 8 | HTTP·스트림 오류 | 반례 확인 | exit 1이어도 `agent_end.stopReason=completed`. assistant의 `error`와 hasError를 함께 봐야 함. `http_error`, `stream_error` |
| 9 | 일시 오류와 재시도 | 확인 | managed fallback에서 503→`auto_retry_start`→정상 응답→`auto_retry_end(success=true)`, 12/12. `worker_transient_error_fallback` |
| 10 | 모델·bash 실행 중 취소 | 반례 확인 | 모델 abort는 assistant `aborted`; bash 취소는 tool error와 `toolUse`만 남음. 둘 다 외부 completed 가능. bash `tool_result`가 `agent_end` 뒤에 온 사례도 있음. `screens/model-cancel-after.txt`, `bash-cancel-after.txt` |
| 11 | 자식 일시정지·재개 | 확인 | pause 요청 결과는 아직 running. 이후 실제 child `agent_end=paused`, inspect=paused, resume 후 completed를 확인. 같은 sessionId에 새 producerId·job ID가 생김. `matrix_pause_boundary` |
| 12 | 자식 한 개 | 확인 | 실제 root+child 세션에서 이벤트 수신. native `parentSession`은 없음. `worker_task_wait_configured` |
| 13 | 자식 여러 개 병렬 | 확인 | root+2 child 세션 관측. `worker_task_pair_configured` |
| 14 | 자식 실패·부모 정상 응답 | 확인 | child assistant error, job failed와 parent 정상 최종 응답이 공존. `worker_task_fail_configured` |
| 15 | 자식 ask 대기·응답 경로 | 부분 | 커스텀 agent에서 실제 child ask 시작 관측. TUI Ctrl+S observer는 pending을 보여 주지만 Enter는 펼치기이며 답변 선택이 아니었다. 질문 해결 E2E는 미확인. `tui_child`, `screens/child-observer-expanded.txt` |
| 16 | 부모→자식→손자 | 확인 | 커스텀 agent로 실제 세 세션의 hook 수신, 60/60. `worker_task_nested_clean`. 세션 종료만으로 모든 child의 최종 성공을 증명할 수는 없음 |
| 17 | 다른 cwd의 격리 자식 | 부분 | rcopy의 실제 `context.cwd`가 격리 경로임을 probe로 확인. committed·uncommitted hook 모두 root+child 수신. 최종 job은 failed여서 격리 작업 성공은 미확인. `matrix_isolation_cwd_uncommitted`, `matrix_isolation_cwd_committed` |
| 18 | 부모 종료 뒤 자식 작업·질문 유지 | 반례 확인 | root completed 이후 child ask가 미해결이고 TUI background job이 남음. 부모 종료로 자식 대기를 지우면 안 됨. print 모드는 미해결 child로 약 16초 뒤 disposal 오류. `tui_child`, `worker_task_wait_ask_clean` |
| 19 | SDK/ACP 권한 승인 요청 | 미실행 | native TUI의 ask와 다른 경로. SDK/ACP permission provider를 연결하는 추가 구성이 필요해 현재 실험으로 승인 요청 전체를 검증하지 않음. 아래 소스 근거 참조 |
| 20 | 확장 명령의 confirm/input | 관측 누락 확인 | 실제 native 명령에서 confirm 수락·input 반환 marker는 기록됐지만 observer는 session_start 1개뿐. ask 훅만으로 모든 UI 대기를 감지할 수 없음. `ui-fixture-markers.jsonl`, `cases/ui_fixture/` |
| 21 | 수신기 늦게 시작 | 확인 | 연결 전 3개 이벤트 큐를 포함해 10/10 수신. snapshot은 아님. `transport_late_receiver` |
| 22 | 수신기 손실·재접속·중복·gap | 반례 확인 | 실제 재접속 후 10개 중 6개만 수신. 누락 이벤트 재전송 없음. dedup·gap 이후 unknown 유지 정책은 별도 자동 검증. `transport_receiver_loss`, `unit-tests.txt` |
| 23 | 강제 종료·새 실행·세션 전환·같은 cwd | 확인 | SIGKILL에 end/shutdown 없음. 재실행은 새 session/producer. Ctrl+N은 같은 프로세스에서 session_switch(new). 같은 cwd의 두 실행은 terminal handle이 같아도 세션은 다름. `transport_sigkill`, `transport_after_sigkill`, `transport_same_cwd_*`, `screens/session-new-completed.txt` |

## 설계를 바꿔야 하는 다섯 가지

1. **미해결 요청을 호출별 집합으로 관리한다.** `sessionId + producerId + toolCallId`로 추적한다. `tool_call`과 `tool_execution_start`를 각각 새 요청으로 세면 두 배가 된다. 정책 모델에서는 10개 실행 중 + 1개 ask도 주황을 유지하고, 두 ask 중 하나만 끝나도 주황을 유지했다. 이것은 관측된 ask 우선 정책이며 모든 ask가 실제로 답변 가능한 승인임을 보장하지 않는다.
2. **종료와 성공을 구분한다.** completed만으로 초록을 켜지 않는다. 마지막 assistant outcome, 도구 종료, 재시도·대기·child 상태를 함께 본다. child `yield` 경로에서는 hook에 `session_shutdown`이 있으면서 해당 child의 `agent_end`는 없는 실행도 관측했다. shutdown을 성공으로 대체할 수 없다.
3. **같은 키 묶음과 부모 트리를 분리한다.** native header의 parentSession은 자식·손자에서도 없었다. 번호 키 묶음은 실행 wrapper가 부여한 launch ID를 상속시키는 설계가 유력하다. terminal env/PID/cwd만으로 root나 부모 관계를 추정하면 안 된다. 이 launch ID 설계 자체는 이번에 구현하지 않았다.
4. **대기 알림과 실제 응답 경로를 분리한다.** 메인 ask는 동작했지만 child ask의 observer에서 답변하는 경로는 확보하지 못했다. 확장 confirm/input은 observer의 상태 훅에 전혀 나타나지 않았다. “모든 사람 요청을 표시하고 누르면 답변”을 현재 지원 범위로 약속하면 안 된다.
5. **연결 복구에는 상태 복구가 필요하다.** producer별 sequence gap, 실행 수명, heartbeat/lease와 재연결 snapshot 또는 replay를 설계해야 한다. 현재 exporter는 ACK 없는 best effort이므로 later completed가 와도 중간 누락을 복구하지 못한다. epoch 변경은 세션 변경과 별도다.

## 실패한 실험 준비와 한계

초기 설정 실패는 성공 사례에서 분리했다. `models.yml`은 provider 모델 배열 스키마를 요구했다. literal `*.ts`가 아닌 hook 파일명은 도구 이름 matcher였다. `task.isolation.mode=none`에서 `isolated:false`도 거절됐고, 기본 executor에는 ask/task/subagent가 활성화돼 있지 않았다. 이후 별도 profile과 project agent로 필요한 실제 경로를 재실행했다.

일반 loopback 503은 GJC가 `local_unavailable`로 분류해 세션 재시도하지 않았다. print와 TUI 양쪽에서 확인했다. `requestMaxRetries=0`이 세션 retry까지 끈다는 해석은 틀리다. 별도 managed fallback profile로 실제 `auto_retry_start/end` 수신을 확인했다.

격리 실행의 처음 `auto` 시도는 child 생성 전에 실패했고 정상 receipt에서 원인을 확인하지 못했다. rcopy와 canonical cwd를 함께 적용한 후 child hook discovery는 재현했지만, 두 조건을 함께 바꿨으므로 최초 원인을 하나로 단정하지 않는다. rcopy child 실행 후에도 최종 job은 failed였다. 키보드 상태와 별개인 격리 실행·patch 통합 성공을 통과로 기록하지 않았다.

초기 print harness의 stdin 상속을 제거하고 nested·child ask·retry를 새 case로 재검증했다. 배포된 재현 driver는 DEVNULL을 사용한다. 모의 모델이 결정한 흐름이므로 실제 LLM의 도구 선택 정확도를 평가한 결과는 아니다.

## 소스 근거

| 판단 | pinned source |
|---|---|
| native hook 설치·API와 축소 context | [hooks 문서](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/docs/hooks.md), [loader.ts](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/extensibility/hooks/loader.ts#L313) |
| tool_execution 계열은 legacy native HookAPI 문서 타입 밖 | [hooks/types.ts](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/extensibility/hooks/types.ts#L470) |
| SDK 권한 승인과 TUI ask의 차이 | [permission provider 경로](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/session/agent-session.ts#L10087), [ACP requestPermission](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/modes/acp/acp-client-bridge.ts#L118) |
| loopback 가용성 오류·세션 재시도 분류 | [agent-session.ts](https://github.com/Yeachan-Heo/gajae-code/blob/f50b17a7fa9faab5935cbf2c358794597b1bd760/packages/coding-agent/src/session/agent-session.ts#L20472) |

## 남긴 파일과 실행 범위

[`REPRODUCE.md`](../experiments/gjc-hooks/REPRODUCE.md)에 재현 방법이 있다. portable harness로도 정상 응답을 다시 실행해 10/10 전송을 확인했다. [`observer.ts`](../experiments/gjc-hooks/observer.ts)는 메타데이터 exporter이고, [`reducer-model.ts`](../experiments/gjc-hooks/reducer-model.ts)는 정책 실험이다. **제품 `src`에는 연결하지 않았다.**

실험용 Orca 터미널, 로컬 모델 서버, 해당 격리 profile의 SDK broker를 종료했다. GJC 코어·전역 설정·기존 분석 터미널은 수정하지 않았다. GJC가 rcopy 중 자체 생성한 `~/.gjc/wt` 임시 경로는 cleanup 기록에서 별도로 확인한다. PR·커밋·하드웨어 E2E는 수행하지 않았다.

다음 구현 단위는 **메인 세션과 관측 가능한 자식 상태를 push로 받아, 사람 요청 우선·누락 시 unknown을 지키는 bridge**다. 자식 질문 응답·범용 승인 포착·완전한 부모 트리는 별도 미확인 기능으로 남긴다.
