# 요구사항과 테스트 연결

> 자동 생성 문서 · 편집 원본: [requirements.json](requirements.json)
> 수정 후 `python scripts/requirements.py --write`로 갱신합니다.

[전체 안내](README.md) · [의사결정](decisions.md) · [기능](functional.md) · [비기능](nonfunctional.md) · [테스트 연결](test-map.md)

총 **45개 요구사항 중 45개**에 자동 테스트가 연결되어 있습니다. 이 수치는 연결 범위이며, 모든 수용 기준이 증명되었다는 비율이 아닙니다.
`pytest`와 `bun` 연결은 CI에서 새로 실행한 JUnit 결과로 확인합니다. 시나리오·물리 기기·문서 검토는 별도 검증이며 자동 PASS로 바꾸지 않습니다.

기준 검증 기록: [gjc-second-audit.md](../../docs/testing/gjc-second-audit.md). dated historical frozen audit; not a new execution

역방향 탐색: 테스트 이름으로 이 문서나 `requirements.json`을 검색하면 영향받는 요구사항을 찾습니다.

<a id="r01"></a>
## R01 · GJC 0.16.4 고정 지원

요구사항: [R01](functional.md#r01)

구현: [cli.py](../../src/orca_keychron_gjc/cli.py) · [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py)

**pytest · 단위** — [test_gjc_cli.py](../../tests/test_gjc_cli.py)

`test_real_install_refuses_unverified_gjc_before_mutation`

주입한 비지원 버전에서 설치 변경 전 거부를 검증한다.

**pytest · 통합** — [test_gjc_doctor_process.py](../../tests/integration/test_gjc_doctor_process.py)

`test_doctor_reports_exact_version_and_missing_components_without_mutation`

실제 CLI subprocess와 로컬 gjc stub으로 정확한 버전 판정 및 비변경을 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4와 Orca runtime이 필요하며 deterministic loopback provider를 사용한 frozen-wheel 실행이다; 실제 모델 계정 검증은 아니다.

<a id="r02"></a>
## R02 · 사용자·프로젝트 root 선택

요구사항: [R02](functional.md#r02)

구현: [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py) · [cli.py](../../src/orca_keychron_gjc/cli.py)

**pytest · 단위** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_explicit_agent_dir_wins_over_profile_environment`

명시적 사용자 root의 우선순위를 임시 경로로 검증한다.

**pytest · 단위** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_gjc_environment_profile_is_used_when_explicit_is_missing`

명시값 부재 시 환경 root 선택을 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_project_install_uses_project_native_directory`

실제 임시 파일시스템에서 project `.gjc` 설치 경계를 검증한다.

<a id="r03"></a>
## R03 · 불변 release와 최소 loader

요구사항: [R03](functional.md#r03)

구현: [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py) · [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [decision-worker.md](../../src/orca_keychron_gjc/assets/decision-worker.md)

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_install_status_idempotency_and_loader_boundary`

임시 native root에서 설치 경로, digest, loader endpoint와 멱등성을 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_upgrade_replaces_owned_release_and_removes_old_files`

소유권이 증명된 이전 release만 upgrade에서 교체되는지 검증한다.

**pytest · 통합** — [test_gjc_install_faults.py](../../tests/test_gjc_install_faults.py)

`test_manifest_shape_and_private_mode_are_part_of_ownership`

manifest 구조와 private mode가 소유권 판정에 포함되는지 검증한다.

<a id="r04"></a>
## R04 · 증명된 소유 파일만 변경

요구사항: [R04](functional.md#r04)

구현: [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py)

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_install_refuses_and_preserves_unowned_conflicts`

비소유 충돌 파일을 byte 단위로 보존하는지 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_modified_owned_file_blocks_install_and_uninstall`

사용자 수정 뒤 install/uninstall 모두 보존적으로 실패하는지 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_symlink_installation_boundaries_are_refused_and_preserved`

symlink 경계와 대상 보존을 임시 파일시스템에서 검증한다.

**pytest · 통합** — [test_gjc_install_faults.py](../../tests/test_gjc_install_faults.py)

`test_manifest_fifo_is_rejected_without_blocking_or_mutating_it`

FIFO manifest를 block 없이 거부하고 변경하지 않는 subprocess 경계를 검증한다.

<a id="r05"></a>
## R05 · private·transactional 설치

요구사항: [R05](nonfunctional.md#r05)

구현: [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py)

**pytest · 통합** — [test_gjc_install_faults.py](../../tests/test_gjc_install_faults.py)

`test_new_managed_directory_chain_is_private_independent_of_umask`

실제 mode를 확인해 0700/0600 생성을 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_failed_upgrade_rolls_back_every_managed_file`

주입한 upgrade 실패 뒤 관리 파일 전부가 복원되는지 검증한다.

**pytest · 통합** — [test_gjc_install_faults.py](../../tests/test_gjc_install_faults.py)

`test_directory_fsync_failure_leaves_recoverable_journal_then_rerun_recovers`

fsync 실패와 다음 실행 복구를 실제 임시 파일로 검증한다.

**pytest · 통합** — [test_gjc_install_faults.py](../../tests/test_gjc_install_faults.py)

`test_recovery_refuses_a_post_crash_user_edit_and_keeps_journal`

중단 후 사용자 edit를 보존하고 journal을 유지하는지 검증한다.

<a id="r06"></a>
## R06 · 비변경 dry-run과 hook 제거

요구사항: [R06](functional.md#r06)

구현: [cli.py](../../src/orca_keychron_gjc/cli.py) · [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py)

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_dry_run_is_read_only_and_describes_owned_files`

실제 임시 트리의 비변경과 계획 출력을 검증한다.

**pytest · 단위** — [test_gjc_cli.py](../../tests/test_gjc_cli.py)

`test_install_dry_run_does_not_require_installed_gjc`

CLI 의존성 주입으로 GJC 미설치 dry-run 경계를 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_uninstall_dry_run_and_clean_removal`

uninstall dry-run 비변경과 실제 소유 자산 제거를 검증한다.

<a id="r07"></a>
## R07 · 분리된 private 설정과 Python 3.9

요구사항: [R07](nonfunctional.md#r07)

구현: [config.py](../../src/orca_keychron_gjc/config.py) · [pyproject.toml](../../pyproject.toml)

**pytest · 단위** — [test_gjc_config.py](../../tests/test_gjc_config.py)

`test_gjc_config_uses_distinct_owned_paths`

기본 경로가 기존 모드와 분리되는지 검증한다.

**pytest · 통합** — [test_gjc_config.py](../../tests/test_gjc_config.py)

`test_gjc_config_round_trip_is_private`

저장·재로드와 실제 private mode를 검증한다.

**pytest · 통합** — [test_gjc_config.py](../../tests/test_gjc_config.py)

`test_config_fifo_is_rejected_without_blocking_or_mutating_it`

FIFO 설정을 subprocess에서 block 없이 거부한다.

**문서 검토 · 문서 검토** — [final-gate-results.json](../../docs/testing/final-gate-results.json)

동결된 과거 gate의 Python 3.9.6/3.13.5 결과 기록이며 이 문서 생성 시 재실행한 것이 아니다.

<a id="r08"></a>
## R08 · 저장 socket의 일관된 상속

요구사항: [R08](functional.md#r08)

구현: [config.py](../../src/orca_keychron_gjc/config.py) · [cli.py](../../src/orca_keychron_gjc/cli.py) · [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py)

**pytest · 단위** — [test_gjc_cli_faults.py](../../tests/test_gjc_cli_faults.py)

`test_saved_socket_reaches_status_clear_install_and_doctor`

주입한 명령 의존성으로 저장 socket 전달 범위를 검증한다.

**pytest · 통합** — [test_gjc_cli_process.py](../../tests/integration/test_gjc_cli_process.py)

`test_saved_socket_with_spaces_and_nondefault_zone_works_in_real_cli`

실제 CLI subprocess와 AF_UNIX endpoint로 공백 경로를 검증한다.

**pytest · 통합** — [test_gjc_doctor_process.py](../../tests/integration/test_gjc_doctor_process.py)

`test_doctor_distinguishes_live_bridge_from_modified_installation_and_socket_override`

저장 endpoint와 explicit override 진단을 실제 subprocess로 구분한다.

<a id="r09"></a>
## R09 · 전용 9개 명령과 진단

요구사항: [R09](functional.md#r09)

구현: [cli.py](../../src/orca_keychron_gjc/cli.py) · [__main__.py](../../src/orca_keychron_gjc/__main__.py)

**pytest · 단위** — [test_gjc_cli.py](../../tests/test_gjc_cli.py)

`test_gjc_cli_exposes_dedicated_commands`

parser의 정확한 하위 명령 surface를 검증한다.

**pytest · 단위** — [test_gjc_cli_faults.py](../../tests/test_gjc_cli_faults.py)

`test_doctor_reports_each_partial_health_dimension`

주입한 부분 건강 조합을 독립 필드로 보고하는지 검증한다.

**pytest · 통합** — [test_gjc_distribution.py](../../tests/integration/test_gjc_distribution.py)

`test_wheel_contains_both_commands_and_exact_current_assets`

fresh non-editable wheel 환경에서 두 entrypoint와 package asset을 검증한다.

**pytest · 통합** — [test_gjc_doctor_process.py](../../tests/integration/test_gjc_doctor_process.py)

`test_doctor_rejects_corrupt_config_without_reporting_healthy_or_rewriting_it`

실제 doctor subprocess가 손상 설정을 재작성하거나 healthy로 오인하지 않는지 검증한다.

<a id="r10"></a>
## R10 · serve의 로컬 전용 경계

요구사항: [R10](functional.md#r10)

구현: [cli.py](../../src/orca_keychron_gjc/cli.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 통합** — [test_gjc_cli_process.py](../../tests/integration/test_gjc_cli_process.py)

`test_serve_and_status_never_load_hardware_or_start_external_commands`

실제 serve/status subprocess에 HID import와 외부 명령 tripwire를 둔다.

**pytest · 단위** — [test_gjc_cli.py](../../tests/test_gjc_cli.py)

`test_serve_collision_is_a_bounded_cli_error_and_preserves_live_bridge`

주입한 endpoint 충돌에서 live bridge 보존과 bounded 오류를 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_stop_preserves_replacement_path_and_restart_is_supported`

실제 AF_UNIX receiver stop/restart와 replacement path 보존을 검증한다.

<a id="r11"></a>
## R11 · checkout 독립 wheel

요구사항: [R11](nonfunctional.md#r11)

구현: [pyproject.toml](../../pyproject.toml) · [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [decision-parent.md](../../src/orca_keychron_gjc/assets/decision-parent.md) · [decision-worker.md](../../src/orca_keychron_gjc/assets/decision-worker.md)

**pytest · 통합** — [test_gjc_distribution.py](../../tests/integration/test_gjc_distribution.py)

`test_wheel_contains_both_commands_and_exact_current_assets`

GJC_TEST_WHEEL_DIR의 non-editable wheel을 별도 venv에 설치해 정확한 byte와 명령을 검증한다.

**pytest · 통합** — [test_gjc_distribution.py](../../tests/integration/test_gjc_distribution.py)

`test_installed_managed_loader_executes_and_streams_to_installed_receiver`

설치 wheel의 managed loader와 실제 local socket receiver 연결을 검증한다.

**문서 검토 · 문서 검토** — [final-gate-results.json](../../docs/testing/final-gate-results.json)

동결된 build, Twine, Python 3.9 install/check 및 isolated help 결과 기록이며 새 실행은 아니다.

<a id="r12"></a>
## R12 · GJC 서비스의 독립·보수적 소유

요구사항: [R12](functional.md#r12)

구현: [autostart.py](../../src/orca_keychron_gjc/autostart.py)

**pytest · 단위** — [test_gjc_autostart.py](../../tests/test_gjc_autostart.py)

`test_launch_agent_uses_separate_gjc_namespace`

정의와 label이 별도 namespace인지 검증한다.

**pytest · 단위** — [test_gjc_autostart.py](../../tests/test_gjc_autostart.py)

`test_install_refuses_loaded_orca_agent_without_booting_it_out`

가짜 launchctl에서 기존 loaded Orca 서비스를 변경하지 않고 거부하는지 검증한다.

**pytest · 통합** — [test_gjc_autostart.py](../../tests/test_gjc_autostart.py)

`test_failed_bootstrap_restores_and_reloads_previous_owned_plist`

임시 plist와 주입 launchctl 실패로 rollback을 검증한다.

**pytest · 단위** — [test_gjc_autostart_faults.py](../../tests/test_gjc_autostart_faults.py)

`test_orca_service_inspection_error_fails_closed_without_writing`

서비스 확인 오류가 쓰기 전 fail closed되는지 검증한다.

<a id="r13"></a>
## R13 · 대화형 root당 publisher 하나

요구사항: [R13](functional.md#r13)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`requires actual interactive Orca identity; explicitly headless fixtures allowed`

제조한 hook context로 interactive/headless 등록 경계를 검증한다.

**pytest · 단위** — [test_gjc_e2e_audit.py](../../tests/e2e/test_gjc_e2e_audit.py)

`test_slots_require_independent_launches_and_survive_restart`

보존된 metadata evidence를 독립 oracle로 검증하며 실제 GJC 실행 자체는 아니다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

unmodified GJC 0.16.4, Orca runtime, frozen wheel과 deterministic loopback provider로 두 실제 launch와 child 집계를 실행한다; 실제 모델은 아니다.

<a id="r14"></a>
## R14 · 중첩 프로세스의 root 사칭 방지

요구사항: [R14](nonfunctional.md#r14)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 통합** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-LINEAGE: real nested process inherits owner marker and cannot claim a root`

실제 Bun child process에서 상속 owner marker의 root 억제를 검증한다.

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`unrelated interactive loader cannot switch, mutate or close the root even with a reused ID`

제조한 서로 다른 loader context의 권한 분리를 검증한다.

**Bun · 단위** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-ID: child reopening current root never takes authority even after resume`

native-shaped event 순서에서 child 재개 뒤에도 root 권한 불획득을 검증한다.

<a id="r15"></a>
## R15 · 같은 프로세스의 session 전환

요구사항: [R15](functional.md#r15)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`normal session switch keeps one root and preserves old unresolved requests`

제조한 native event로 session switch와 pending 보존을 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_root_session_switch_is_not_mistaken_for_a_new_process_generation`

tracker가 root session 변경을 새 process generation으로 오인하지 않는지 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4와 deterministic loopback provider에서 실제 `/new`, `/resume`, `/exit`을 실행한다; 실제 모델 계정은 사용하지 않는다.

<a id="r16"></a>
## R16 · user·project loader 중복 억제

요구사항: [R16](functional.md#r16)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`separate installed loaders share a publisher and duplicate events`

두 loader instance와 중복 이벤트를 제조해 단일 publisher/count를 검증한다.

**Bun · 단위** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-LOADER: original payloads establish duplicate root provenance in both delivery orders`

원본 payload의 양방향 delivery order에서 provenance를 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4가 user/project 설치 hook을 실제로 중복 발견하는 상황을 deterministic loopback provider로 실행한다.

<a id="r17"></a>
## R17 · pending ask 중복 방지

요구사항: [R17](functional.md#r17)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`duplicate loaders and repeated or late starts never double count asks`

중복 loader와 반복·지연 이벤트의 pending count를 검증한다.

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`tool name mismatch cannot clear a pending ask`

tool 이름 불일치가 matching call을 해제하지 못하는 negative case다.

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`resolved-call memory is bounded and exhaustion explicitly downgrades coverage`

bounded receipt history 초과가 false completeness가 아닌 incomplete로 표시되는지 검증한다.

<a id="r18"></a>
## R18 · 미해결 human request 유지

요구사항: [R18](functional.md#r18)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`child shutdown and parent completion retain decision; only matching real answer clears it`

synthetic result.details를 이용해 pending 보존과 matching 해제를 검증한다.

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`multi-answer correlation clears only matching decision and collisions stay uncertain`

여러 결정의 cross-answer와 collision negative case를 검증한다.

**pytest · 단위** — [test_gjc_tracker.py](../../tests/test_gjc_tracker.py)

`test_priority_child_asks_survive_root_done_and_full_recovery`

tracker full snapshot 교체와 root done 뒤 child waiting 보존을 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4의 두 실제 child/request를 deterministic fixture answer로 순서대로 해결한다; 실제 사용자의 답변이나 모델은 아니다.

<a id="r19"></a>
## R19 · 검증된 yield만 성공 인정

요구사항: [R19](functional.md#r19)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`malformed yield is unknown, child shutdown alone never proves success`

malformed payload와 shutdown-only negative case를 검증한다.

**Bun · 단위** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-YIELD: malformed yield receipt stays unknown 0`

native-shaped null receipt가 unknown으로 남는 실행된 parameterized case를 검증한다.

**pytest · 단위** — [test_gjc_successor_fixture.py](../../tests/test_gjc_successor_fixture.py)

`test_launch_a_asks_only_after_actual_child_and_exact_pending_envelope`

독립 fixture oracle이 실제 child ID와 정확한 decision envelope를 요구한다.

<a id="r20"></a>
## R20 · 최종 outcome과 retry 해석

요구사항: [R20](functional.md#r20)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`final assistant outcome, retry, late failures, pause and queued work`

제조한 native event 순서로 주요 outcome과 중간 상태를 검증한다.

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`cancelled ask followed by completed toolUse is never green`

cancel 이후 toolUse completed가 done을 만들지 않는 negative case다.

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`exhausted retry remains failed when an outstanding tool ends late`

retry 소진 뒤 늦은 tool 종료의 상태 회귀를 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4와 loopback provider로 success, failure, cancellation을 실행한다; provider는 deterministic이고 실제 모델은 아니다.

<a id="r21"></a>
## R21 · opt-in worker와 root-only 지침

요구사항: [R21](functional.md#r21)

구현: [decision-parent.md](../../src/orca_keychron_gjc/assets/decision-parent.md) · [decision-worker.md](../../src/orca_keychron_gjc/assets/decision-worker.md) · [gjc_install.py](../../src/orca_keychron_gjc/gjc_install.py) · [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`parent instructions append without replacing prompt and stay root-only`

제조한 hook prompt context로 append와 root-only 적용을 검증한다.

**pytest · 통합** — [test_gjc_install.py](../../tests/test_gjc_install.py)

`test_dry_run_is_read_only_and_describes_owned_files`

decision worker와 parent asset이 설치 계획에 포함되면서 dry-run이 비변경임을 검증한다.

**문서 검토 · 문서 검토** — [decision-worker.md](../../src/orca_keychron_gjc/assets/decision-worker.md)

배포되는 worker의 tool 선언과 result.data 계약 원문이다.

<a id="r22"></a>
## R22 · 실제 child와 답의 정확한 상관

요구사항: [R22](functional.md#r22)

구현: [decision-parent.md](../../src/orca_keychron_gjc/assets/decision-parent.md) · [decision-worker.md](../../src/orca_keychron_gjc/assets/decision-worker.md)

**pytest · 단위** — [test_gjc_e2e_audit.py](../../tests/e2e/test_gjc_e2e_audit.py)

`test_decision_oracle_rejects_cross_answer_and_duplicate_resume`

보존 evidence용 독립 oracle이 cross-answer와 중복 resume를 거부한다.

**pytest · 단위** — [test_gjc_successor_fixture.py](../../tests/test_gjc_successor_fixture.py)

`test_successor_accepts_only_all_correlated_fields`

request, checkpoint, answer, continuation의 전 필드 상관을 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4에서 실제 두 child ID를 읽고 loopback fixture answer로 각각 재개한다; 실제 모델 준수 검증은 아니다.

<a id="r23"></a>
## R23 · 사라진 child의 successor 전환

요구사항: [R23](functional.md#r23)

구현: [decision-parent.md](../../src/orca_keychron_gjc/assets/decision-parent.md) · [decision-worker.md](../../src/orca_keychron_gjc/assets/decision-worker.md)

**pytest · 단위** — [test_gjc_successor_fixture.py](../../tests/test_gjc_successor_fixture.py)

`test_actual_gjc_not_found_receipt_requires_successor_path`

이 검증 harness는 이전 child의 부재를 실제 native not_found receipt로 확인한다. 이는 실험의 oracle이며 모든 제품 흐름에 실패한 resume 시도를 강제하는 요구사항은 아니다.

**pytest · 단위** — [test_gjc_successor_fixture.py](../../tests/test_gjc_successor_fixture.py)

`test_launch_b_rejects_successor_identity_collision`

predecessor와 동일한 successor identity를 거부한다.

**pytest · 단위** — [test_gjc_successor_fixture.py](../../tests/test_gjc_successor_fixture.py)

`test_successor_rejects_wrong_checkpoint_even_with_known_answer`

답이 맞아도 checkpoint가 틀리면 승계를 거부한다.

**별도 실행 시나리오 · 실제 실행** — [harness.py](../../experiments/gjc-successor-audit/harness.py)

unmodified GJC 0.16.4와 Orca runtime, frozen-wheel payload, deterministic loopback provider가 필요하다; launch A 종료 뒤 launch B successor를 실제 실행하며 자동 persistence나 실제 모델은 증명하지 않는다. 이 fixture에서 request ID·checkpoint·answer·continuation 종류를 비교하지만, continuation 종류는 제품의 보편적인 payload 필드로 요구하지 않는다.

<a id="r24"></a>
## R24 · 엄격한 full snapshot JSONL v1

요구사항: [R24](nonfunctional.md#r24)

구현: [gjc_protocol.py](../../src/orca_keychron_gjc/gjc_protocol.py) · [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**pytest · 단위** — [test_gjc_protocol.py](../../tests/test_gjc_protocol.py)

`test_no_content_extensions_duplicate_keys_or_sessions`

확장 필드, 중복 key와 session을 strict parser가 거부하는지 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_duplicate_sessions_and_nonunique_or_missing_root_are_rejected`

root uniqueness와 duplicate session negative variants를 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_snapshot_bytes_require_utf8_json_lines_encoding`

UTF-8 JSONL byte encoding 경계를 검증한다.

**Bun · 통합** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`emitted snapshots satisfy the actual Python receiver schema, including closed pending child`

Bun producer 출력이 Python parser subprocess의 실제 schema를 통과하는 cross-language test다.

<a id="r25"></a>
## R25 · content-free 상태 전송

요구사항: [R25](nonfunctional.md#r25)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [gjc_protocol.py](../../src/orca_keychron_gjc/gjc_protocol.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [cli.py](../../src/orca_keychron_gjc/cli.py)

**pytest · 단위** — [test_gjc_e2e_audit.py](../../tests/e2e/test_gjc_e2e_audit.py)

`test_evidence_allowlist_drops_content_and_arbitrary_fields`

합성 evidence에서 content와 임의 필드를 제거하는 독립 allowlist oracle이다.

**pytest · 통합** — [test_gjc_distribution.py](../../tests/integration/test_gjc_distribution.py)

`test_installed_managed_loader_executes_and_streams_to_installed_receiver`

설치 loader에 넣은 question/option sentinel이 registry와 status에 나타나지 않는지 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4와 loopback provider의 actual wire를 metadata-only allowlist로 보존한다; sanitizer 자체가 제품 보안 경계는 아니다.

<a id="r26"></a>
## R26 · 변경 push와 정확한 2초 heartbeat

요구사항: [R26](nonfunctional.md#r26)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 통합** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`socket reconnect replaces lost history with latest complete snapshot and flushes closure`

local socket 재연결에서 최신 full snapshot과 closure flush를 검증하며 heartbeat는 30ms로 override한다.

**Bun · 통합** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-TRANSPORT: event-synchronized Unix reconnect sends latest full state and closed flush`

실제 Unix socket과 event synchronization으로 stale replay 부재를 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4를 receiver 부재 상태에서 시작한 뒤 reconnect하는 실제 runtime 경로다; loopback provider이며 정확한 2초 timer 계측은 아니다.

**문서 검토 · 문서 검토** — [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md)

2초 heartbeat와 bounded reconnect의 normative 계약이며 실행 증거가 아니다.

<a id="r27"></a>
## R27 · backpressure 병합과 bounded 종료

요구사항: [R27](nonfunctional.md#r27)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts)

**Bun · 단위** — [gjc_hook.test.ts](../../tests/gjc_hook.test.ts)

`backpressure coalesces to one latest frame and bounded shutdown completes without receiver`

fake socket의 write(false)와 내부 drain으로 coalescing branch를 검증한다.

**Bun · 통합** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-LIVENESS: real Bun process exits with absent receiver without disposal`

실제 Bun child process와 absent receiver에서 event-loop liveness를 검증한다.

**Bun · 통합** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-BACKPRESSURE: real paused receiver bounds buffered frames and shutdown exits`

실제 paused Unix receiver에서 buffer bound와 child shutdown을 검증한다.

<a id="r28"></a>
## R28 · session·call·frame·ID cap

요구사항: [R28](nonfunctional.md#r28)

구현: [gjc_hook.ts](../../src/orca_keychron_gjc/assets/gjc_hook.ts) · [gjc_protocol.py](../../src/orca_keychron_gjc/gjc_protocol.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_identifier_and_collection_limits_are_exact`

512자 ID와 256 session의 경계값·초과값을 독립적으로 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_request_counter_bounds_are_exact`

pending counter의 정확한 128 단위 경계를 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_exact_frame_cap_then_healthy_continuation`

실제 socket에서 정확히 512 KiB frame 경계와 초과 client 격리 후 정상 continuation을 검증한다.

**Bun · 단위** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-BOUNDS: independent session tool IDs deduplicate, overflow remains incomplete`

session별 tool ID 분리와 publisher overflow의 incomplete 표시를 검증한다.

<a id="r29"></a>
## R29 · private socket과 안전한 stale 복구

요구사항: [R29](nonfunctional.md#r29)

구현: [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [config.py](../../src/orca_keychron_gjc/config.py)

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_second_receiver_never_unlinks_live_socket`

실제 AF_UNIX listener 두 개의 contention에서 첫 endpoint 보존을 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_stale_socket_recovery_and_unowned_file_refusal`

stale owned socket 복구와 foreign file 거부를 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_bind_leaf_replacement_never_chmods_or_removes_replacement`

bind race에 주입한 leaf replacement의 mode와 byte 보존을 검증한다.

**pytest · 통합** — [test_device_lock.py](../../tests/test_device_lock.py)

`test_rejects_symlink_lock_without_changing_target`

공유 private-path 정책의 symlink target 비변경 경계를 검증한다.

<a id="r30"></a>
## R30 · client·buffer 제한과 격리

요구사항: [R30](nonfunctional.md#r30)

구현: [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_bad_frame_drops_only_offender_and_next_launch_works`

실제 socket에서 malformed client 격리 뒤 새 정상 launch를 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_non_utf8_snapshot_is_rejected_without_registry_write`

non-UTF-8 client가 registry를 변경하지 않는지 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_client_cap_and_partial_stalls_release_capacity_with_injected_clock`

실제 connections와 injected monotonic clock으로 client cap과 partial stall 회수를 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_receiver_surfaces_storage_failure_and_marks_unknown`

주입 storage failure가 receiver 전체를 묵살하지 않고 unknown과 typed failure로 드러나는지 검증한다.

<a id="r31"></a>
## R31 · 정확한 8초 monotonic lease

요구사항: [R31](functional.md#r31)

구현: [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 단위** — [test_gjc_tracker.py](../../tests/test_gjc_tracker.py)

`test_fractional_lease_deadline_uses_absolute_bounds`

주입 monotonic 값으로 fractional 8초 deadline 전후를 정확히 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_lease_uses_local_receive_clock_and_retains_slot`

실제 receiver와 injected local clock으로 producer timestamp 비신뢰와 slot 보존을 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_fractional_lease_disconnect_and_reconnection_trace`

disconnect, exact deadline, reconnect의 생성 trace를 독립 oracle로 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

actual GJC producer kill과 receiver restart/backfill을 loopback provider로 실행하지만 정확한 8초 timer 경계 측정은 unit/integration clock tests가 담당한다.

<a id="r32"></a>
## R32 · sequence·generation 회귀 방지

요구사항: [R32](nonfunctional.md#r32)

구현: [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 단위** — [test_gjc_tracker.py](../../tests/test_gjc_tracker.py)

`test_changed_producer_and_launch_metadata_cannot_seize`

producer·launch metadata 변조의 takeover negative cases를 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_duplicate_reconnect_cannot_disconnect_live_owner`

실제 두 connection의 obsolete close ordering을 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_complete_snapshot_recovers_an_incomplete_gap_but_replays_cannot_regress`

complete frame의 gap recovery와 replay regression 방지를 함께 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_identity_change_disconnects_original_but_preserves_other_root`

identity change가 관련 root만 격리하고 다른 root를 보존하는지 검증한다.

<a id="r33"></a>
## R33 · 원자 registry와 안정적 slot

요구사항: [R33](functional.md#r33)

구현: [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 단위** — [test_gjc_tracker.py](../../tests/test_gjc_tracker.py)

`test_stable_slots_shared_session_id_overflow_clear_and_closure`

stable slot, shared session ID, overflow와 explicit closure를 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_stop_restart_restores_unknown_and_new_complete_snapshot`

실제 source restart 뒤 unknown restore와 fresh frame recovery를 검증한다.

**pytest · 통합** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_failed_registry_replace_leaves_no_partial_file_and_next_frame_recovers`

주입 replace 실패 뒤 partial file 부재와 다음 frame 복구를 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

actual GJC 두 launch의 stable slots와 receiver restart/backfill을 loopback provider로 실행한다.

<a id="r34"></a>
## R34 · process crash와 endpoint 분리

요구사항: [R34](nonfunctional.md#r34)

구현: [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_process_crash_releases_lock_and_preserves_registry`

실제 subprocess crash 뒤 lock 회수와 registry byte 보존을 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_shared_registry_refuses_distinct_endpoint_without_mutation`

서로 다른 live endpoint의 shared registry 접근을 변경 없이 거부한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_failed_restore_releases_registry_lock`

손상 restore 실패가 registry lock을 누수하지 않는지 검증한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_storage_failure_foreground_and_restart_recovers_committed_state`

foreground storage failure와 restart에서 마지막 committed 상태 복구를 검증한다.

<a id="r35"></a>
## R35 · 명시적 close만 slot 반환

요구사항: [R35](functional.md#r35)

구현: [gjc_protocol.py](../../src/orca_keychron_gjc/gjc_protocol.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_explicit_close_releases_slot_without_resurrection`

실제 socket frame으로 explicit close, vacancy와 늦은 resurrection 거부를 검증한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_explicit_root_closure_reclaims_slot_even_with_a_pending_child`

pending child가 있어도 explicit root closure의 slot 회수를 검증한다.

**pytest · 단위** — [test_gjc_protocol.py](../../tests/test_gjc_protocol.py)

`test_explicit_closed_empty_snapshot`

closed empty snapshot의 정확한 protocol shape를 검증한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

actual GJC의 explicit `/exit` close와 별도 producer kill unknown을 loopback provider로 구분해 실행한다.

<a id="r36"></a>
## R36 · OS로 종료가 증명된 launch만 clear

요구사항: [R36](functional.md#r36)

구현: [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py) · [cli.py](../../src/orca_keychron_gjc/cli.py)

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_live_clear_refusal_preserves_heartbeat_even_after_lease_expiry`

live connection의 lease 만료 뒤 clear 거부와 후속 heartbeat 처리를 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_disconnected_owned_child_only_clears_after_exit`

실제 child process가 살아 있을 때 거부하고 종료 뒤 ESRCH로 clear하는지 검증한다.

**pytest · 단위** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_disconnected_ambiguous_pid_refuses_without_mutation`

permission·ambiguous OS 오류 주입에서 registry 비변경을 검증한다.

**pytest · 통합** — [test_gjc_distribution.py](../../tests/integration/test_gjc_distribution.py)

`test_installed_cli_preserves_human_priority_and_rejects_live_clear`

installed wheel CLI가 live clear를 거부하고 상태 우선순위를 보존한다.

<a id="r37"></a>
## R37 · 엄격하고 직렬화된 control

요구사항: [R37](functional.md#r37)

구현: [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py) · [cli.py](../../src/orca_keychron_gjc/cli.py)

**pytest · 단위** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_control_client_strictly_rejects_malformed_clear_rejections`

clear 거절 response의 필드·타입·error reason 변형을 거부한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_status_client_rejects_negative_or_clear_response_shapes`

실제 socket client가 status에 잘못 온 negative·clear shape를 거부한다.

**pytest · 통합** — [test_gjc_transport_faults.py](../../tests/test_gjc_transport_faults.py)

`test_clear_serializes_before_queued_reconnect_without_resurrection`

event-gated socket race에서 clear가 queued reconnect보다 먼저 직렬화되고 부활하지 않음을 검증한다.

**pytest · 단위** — [test_gjc_cli.py](../../tests/test_gjc_cli.py)

`test_clear_live_producer_reports_rejection_not_unreachable`

CLI가 clear refusal과 unreachable을 다른 메시지와 exit로 처리하는지 검증한다.

<a id="r38"></a>
## R38 · live·offline 상태의 명확한 구분

요구사항: [R38](functional.md#r38)

구현: [cli.py](../../src/orca_keychron_gjc/cli.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**pytest · 단위** — [test_gjc_cli.py](../../tests/test_gjc_cli.py)

`test_status_falls_back_to_registry_and_labels_it_offline`

주입 offline status에서 registry source label을 검증한다.

**pytest · 통합** — [test_gjc_cli_process.py](../../tests/integration/test_gjc_cli_process.py)

`test_cli_crash_restart_preserves_slots_then_reclaims_only_dead_launch`

실제 CLI subprocess, SIGKILL, registry restore와 dead-only clear를 검증한다.

**pytest · 통합** — [test_gjc_cli_process.py](../../tests/integration/test_gjc_cli_process.py)

`test_plain_live_status_marks_incomplete_coverage_until_complete_followup`

plain live status가 incomplete marker를 표시하고 fresh complete frame 뒤 제거하는지 검증한다.

**pytest · 통합** — [test_gjc_source.py](../../tests/test_gjc_source.py)

`test_control_timeout_is_bounded`

응답하지 않는 local socket의 bounded timeout을 검증한다.

<a id="r39"></a>
## R39 · 사람 요청 우선 집계

요구사항: [R39](functional.md#r39)

구현: [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_all_priority_subsets_and_order_permutations_match_independent_oracle`

1,956개 subset/order permutation을 생산 코드와 독립 oracle로 비교한다.

**pytest · 단위** — [test_gjc_state_invariants.py](../../tests/test_gjc_state_invariants.py)

`test_incomplete_and_uncertain_states_obey_the_same_priority_boundary`

incomplete·paused·cancelled·unknown 조합의 priority와 false success 방지를 검증한다.

**Bun · 단위** — [gjc_hook_faults.test.ts](../../tests/gjc_hook_faults.test.ts)

`H-PRIORITY: pending ask remains waiting over failure, cancellation and retry`

native-shaped event에서 ask가 failure/cancel/retry보다 우선함을 검증한다.

**pytest · 단위** — [test_gjc_e2e_audit.py](../../tests/e2e/test_gjc_e2e_audit.py)

`test_mass_oracle_rejects_later_orange_frame_with_different_count`

다른 시점의 orange frame을 동일 snapshot 증거로 오인하는 oracle을 거부한다.

**별도 실행 시나리오 · 실제 실행** — [run_audit.py](../../experiments/gjc-e2e-audit/run_audit.py)

GJC 0.16.4에서 캡처한 exact sequence 117을 installed tracker/renderer로 replay한다; live same-frame LED 관측이나 optical 검증은 아니다.

<a id="r40"></a>
## R40 · 상태별 색상과 빈 slot 표시

요구사항: [R40](functional.md#r40)

구현: [rendering.py](../../src/orca_keychron/rendering.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**pytest · 단위** — [test_rendering.py](../../tests/test_rendering.py)

`test_gjc_additional_states_are_distinct_from_orca_and_success`

GJC 추가 상태 색이 기존 Orca와 success 색에서 구별되는지 검증한다.

**pytest · 단위** — [test_rendering.py](../../tests/test_rendering.py)

`test_render_zone_uses_sky_blue_for_unassigned_number_slots`

빈 number row slot의 sky-blue 기본 렌더링을 검증한다.

**pytest · 통합** — [test_gjc_runtime_integration.py](../../tests/test_gjc_runtime_integration.py)

`test_actual_receiver_snapshot_drives_palette_fake_hid_and_navigation`

실제 AF_UNIX receiver에서 fake HID까지 push된 palette를 검증하며 물리 HID는 아니다.

**수동 확인 · 물리 기기** — [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md)

과거 Q65 Max의 다섯 RGB frame firmware ACK와 조명 복구 기록이다; 육안 색상과 실제 키 입력은 수행하지 않았다.

<a id="r41"></a>
## R41 · push-only 표시와 실패 복구

요구사항: [R41](nonfunctional.md#r41)

구현: [indicator.py](../../src/orca_keychron/indicator.py) · [rendering.py](../../src/orca_keychron/rendering.py) · [gjc_source.py](../../src/orca_keychron_gjc/gjc_source.py)

**pytest · 단위** — [test_indicator.py](../../tests/test_indicator.py)

`test_gjc_consumes_pushed_model_and_expires_lease_without_orca_polling`

fake source/model로 GJC mode가 Orca poll 없이 push 상태를 소비하는지 검증한다.

**pytest · 단위** — [test_indicator.py](../../tests/test_indicator.py)

`test_gjc_runtime_failure_always_closes_source_and_device`

주입 runtime fault에서 source와 device close를 검증한다.

**pytest · 통합** — [test_keychron_hid_faults.py](../../tests/test_keychron_hid_faults.py)

`test_indicator_short_usb_write_restores_lighting_stops_source_and_releases_lock`

fake HID short-write fault에서 restoration, source stop과 lock release를 검증한다.

**수동 확인 · 물리 기기** — [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md)

과거 실제 Q65 Max firmware ACK와 조명 restore 기록이며 unplug·실제 GJC key input 검증은 아니다.

<a id="r42"></a>
## R42 · 공유 cooperative device lock

요구사항: [R42](nonfunctional.md#r42)

구현: [device_lock.py](../../src/orca_keychron/device_lock.py) · [keychron_hid.py](../../src/orca_keychron/keychron_hid.py) · [indicator.py](../../src/orca_keychron/indicator.py)

**pytest · 통합** — [test_device_lock.py](../../tests/test_device_lock.py)

`test_two_actual_processes_contend_then_release_allows_new_owner`

실제 두 Python process의 lock contention과 release 후 새 owner를 검증한다.

**pytest · 통합** — [test_device_lock.py](../../tests/test_device_lock.py)

`test_sigkill_owner_releases_lock_without_removing_file`

실제 subprocess SIGKILL 뒤 inode 보존과 lock 회수를 검증한다.

**pytest · 단위** — [test_keychron_hid.py](../../tests/test_keychron_hid.py)

`test_contender_is_rejected_before_hid_enumeration_or_open`

fake HID로 contender가 enumeration/open 전에 거부되는지 검증한다.

**pytest · 통합** — [test_device_lock.py](../../tests/test_device_lock.py)

`test_rejects_fifo_without_blocking`

FIFO lock path를 block 없이 거부한다.

<a id="r43"></a>
## R43 · launch의 부모 pane으로 이동

요구사항: [R43](functional.md#r43)

구현: [digit_hold.py](../../src/orca_keychron/digit_hold.py) · [orca_navigation.py](../../src/orca_keychron/orca_navigation.py) · [gjc_tracker.py](../../src/orca_keychron_gjc/gjc_tracker.py)

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_selection_accepts_gjc_without_worktree_identity`

GJC launch target이 별도 worktree ID 없이 부모 pane metadata로 선택되는지 검증한다.

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_immediate_selection_cancels_when_target_disappears_before_dispatch`

선택 후 dispatch 전 target disappearance을 취소하는 race를 검증한다.

**pytest · 단위** — [test_orca_navigation.py](../../tests/test_orca_navigation.py)

`test_navigator_refreshes_handle_and_switches_worktree_tab`

가짜 Orca CLI 응답으로 handle refresh와 정확한 tab switch를 검증한다.

**수동 확인 · 물리 기기** — [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md)

과거 실제 Orca target pane 이동과 원래 pane 복귀 기록이며 physical Option key path는 아니다.

<a id="r44"></a>
## R44 · 1~0,-,= 단축키와 입력 보존

요구사항: [R44](functional.md#r44)

구현: [digit_hold.py](../../src/orca_keychron/digit_hold.py)

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_option_minus_and_equal_use_mac_physical_keycodes`

macOS physical keycode의 -와 = slot 매핑을 검증한다.

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_option_digit_passes_through_when_orca_is_not_frontmost`

fake Quartz event에서 다른 앱 frontmost 입력 통과를 검증한다.

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_mac_filter_passes_unmapped_and_extra_modifier_events_through`

unmapped key와 Shift/Control/Command 조합을 통과시키는지 검증한다.

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_mac_repeat_does_not_advance_target_until_keyup`

keydown repeat가 keyup 전 추가 이동하지 않는지 검증한다.

**pytest · 단위** — [test_digit_hold.py](../../tests/test_digit_hold.py)

`test_listener_wait_failure_stops_started_native_listener`

listener wait 실패 뒤 시작한 native listener 정리를 검증한다.

<a id="r45"></a>
## R45 · 검증 층과 미검증 경계의 분리

요구사항: [R45](nonfunctional.md#r45)

구현: [gjc-keychron-development-ticket.md](../../docs/gjc-keychron-development-ticket.md) · [gjc-bridge-contract.md](../../docs/gjc-bridge-contract.md) · [gjc-guide.md](../../docs/gjc-guide.md) · [gjc-second-audit.md](../../docs/testing/gjc-second-audit.md)

**pytest · 단위** — [test_requirements_traceability.py](../../tests/test_requirements_traceability.py)

`test_registry_refuses_lost_history_broken_links_and_overclaimed_proof`

자동 테스트를 runtime/hardware 증거로 잘못 분류하거나 요구사항·결정 연결을 잃는 구조적 오류를 거부한다. 모든 지원 범위 문구의 진실성은 문서 검토로 별도 확인한다.

**pytest · 단위** — [test_requirements_traceability.py](../../tests/test_requirements_traceability.py)

`test_generated_text_must_follow_the_single_registry`

JSON 원본과 생성 문서의 불일치를 거부한다. 원본 자체의 의미가 옳은지는 독립 리뷰가 필요하다.

**문서 검토 · 문서 검토** — [gjc-second-audit.md](../../docs/testing/gjc-second-audit.md)

동결된 2026-09-06 감사 결과와 남은 proof boundary를 기록한 역사 문서이며 이 registry 작성 중 행동 검증을 재실행하지 않았다.

**문서 검토 · 문서 검토** — [gjc-requirements-matrix.md](../../docs/testing/gjc-requirements-matrix.md)

R01-R45의 원래 audit row와 final addendum를 함께 보존한 근거 문서다.

**문서 검토 · 문서 검토** — [gjc-hardware-validation.md](../../docs/gjc-hardware-validation.md)

과거 bounded hardware/navigation 증거와 physical·optical 미검증 경계를 명시한다.

**문서 검토 · 문서 검토** — [FINAL_REPORT.md](../../experiments/gjc-e2e-audit/FINAL_REPORT.md)

frozen actual-GJC loopback scenario의 결과와 replay 한계를 기록하며 현재 새 실행이 아니다.

**문서 검토 · 문서 검토** — [REPORT.md](../../experiments/gjc-successor-audit/REPORT.md)

restart/successor actual-GJC fixture 결과와 자동 persistence·실제 모델 한계를 기록한 역사 증거다.
