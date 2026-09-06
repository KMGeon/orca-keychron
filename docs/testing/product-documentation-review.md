# 제품 문서·추적성 검사 독립 최종 리뷰

상태: 독립 최종 리뷰 완료. 발견한 medium 4건(검사 코드 2건, 문서 의미 2건)은 모두 수정되어 재확인했으며 미해결 actionable finding은 없다. 작성자는 이 보고서만 수정하며 제품 코드·테스트·생성 문서를 수정하지 않았다.

## 범위와 판단 기준

요청으로 한정된 14개 파일을 검토했다: `scripts/requirements.py`, `tests/test_requirements_traceability.py`, `.github/workflows/tests.yml`, `.github/workflows/publish.yml`, 루트 `README.md`, `docs/README.md`, `docs/product/README.md`, `maintenance.md`, 두 JSON 원본과 네 생성 Markdown 문서. 현재 브랜치의 제품 전체를 새로 감사한 보고서가 아니다.

결정과 수용 기준은 `docs/gjc-keychron-development-ticket.md`, `docs/gjc-bridge-contract.md`, `docs/gjc-guide.md`, `docs/testing/gjc-requirements-matrix.md`의 R01–R45 및 필요한 제품 자산과 대조했다. 초기 초안 부재는 결함으로 취급하지 않았으며 코디네이터가 45개 요구사항·25개 결정과 네 생성 문서 준비 완료를 알린 뒤 최종 산출물을 읽었다. 2026-09-06 06:09 KST 수정 완료 통지 후 최종 수정분과 R45의 구조적 테스트 연결도 확인했다.

새 변경에서 도입된 재현 가능한 정확성 문제만 결함으로 보고했다. 미실행 환경이나 이미 명시된 지원 제한은 결함으로 바꾸지 않는다.

## 발견 사항과 처리

| 항목 | 영향 | 근거 | 처리 상태 |
|---|---|---|---|
| G1 · 실행 helper가 입력 해시에서 누락 | 실험 helper를 실행 중 수정해도 현재 소스와 실행 결과가 일치한다는 검사가 통과할 수 있다. | 최초 `scripts/requirements.py:401`의 대상 폴더에 `experiments`가 없었다. `tests/e2e/test_gjc_e2e_audit.py:10`은 `experiments/gjc-e2e-audit/audit_support.py`를, `tests/test_gjc_successor_fixture.py:7`은 `experiments/gjc-successor-audit/harness.py`를 직접 로드한다. 임시 helper를 `VALUE=1`에서 `VALUE=2`로 바꿔도 해시는 같았다. | medium · 수정/재확인: experiment Python/TypeScript 입력을 추가하고 evidence 경로는 제외 |
| G2 · 매개변수 ID의 `::` 오해석 | 실제 통과한 정확한 pytest 사례가 `test not executed`로 거부된다. | 최초 `scripts/requirements.py:370`이 selector 전체를 `::`로 나눈다. 실제 pytest가 만든 JUnit의 `classname=tests.test_behavior`, `name=test_waiting[foo::bar]`는 함수 전체 selector로 통과하고 정확한 사례 selector로 실패했다. | medium · 수정/재확인: bracket 이전 identity만 분리하며 새 실제 pytest XML의 정확한 사례 연결 통과 |
| D1 · 현행 native hook 결정의 상태 오류 | 의사결정 목록이 현행 관찰 경로 자체를 대체된 결정으로 표시한다. | `docs/product/decisions.json`의 D02는 native hook을 사용하는 현재 결정을 서술하면서 `status=superseded`였고, 생성 문서는 이를 그대로 “대체됨”으로 표시했다. 폐기된 것은 초기 extension/core observer 대안이다. | medium · 수정/재확인: 현재 선택은 accepted, 폐기된 대안은 이유와 함께 보존 |
| D2 · R23에 실험 전용 절차가 제품 필수 동작으로 혼입 | 유효한 명시적 successor 전달에도 불필요한 failed-resume probe와 harness 전용 필드를 요구한다. | R23 수용 기준은 선행 native `not_found`와 continuation 종류 검증을 요구했다. `src/orca_keychron_gjc/assets/decision-parent.md:28`은 이전 child를 재개할 수 없을 때 checkpoint와 실제 답을 가진 successor를 명시적으로 시작하도록 하며 이 probe나 필드를 강제하지 않는다. | medium · 수정/재확인: generic successor 수용 기준과 실험 전용 검증 절차를 분리 |

모든 사항을 코디네이터에게 재현 근거와 함께 전달했고 수정은 코디네이터가 수행했다. G1/G2는 각각 `test_input_receipt_tracks_executed_experiment_helpers_not_old_evidence`, `test_exact_parameter_id_can_contain_double_colons`로 회귀를 방지한다. 문서 두 건은 수정된 JSON과 생성 문서, 실제 parent 자산을 대조했다.

## 직접 실행한 검증

| 검사 | 결과와 실제 경계 |
|---|---|
| `/tmp/gjc-test-audit/final-py313/bin/python -m pytest -q tests/test_requirements_traceability.py` | 최초 14 passed, 0.03초 → 수정 후 16 passed, 0.04초. 레지스트리 ID 보존·중복·없는 selector·없는 요구사항 참조·결정 문맥 누락·하드웨어 과장·생성 문서 불일치·잘못된 파일·실패/skip parameter·Bun 이름/파일·기존 보고서 디렉터리 거부 및 두 신규 회귀를 검사했다. |
| 임시 실제 pytest 실행 | 테스트 한 개로 새 JUnit을 생성해 `test_waiting[foo::bar]`의 정확한 parameter 연결 실패를 재현했다. 수정 후 별도 임시 디렉터리에서 다시 pytest를 실행해 동일 정확한 연결의 통과를 확인했다. 제품 suite를 실행한 결과가 아니다. |
| 임시 입력 해시 반례 | 최초 experiment helper 누락과 임시 helper 변경 미검출을 재현했다. 수정 후 두 실제 import 대상이 receipt에 포함됨을 확인했고 추가 회귀 테스트가 helper 변경 감지와 과거 evidence 제외를 검증했다. |
| 임시 runner fault injection | subprocess를 대역으로 바꾼 검사에서 nonzero pytest, 실행 도중 `src` 변경, 빈 JUnit을 모두 거부했다. 이는 검사 제어 흐름 검증이며 실제 제품 테스트 실행 증거가 아니다. |
| JSON/생성 문서 검사와 링크 순회 | 최종 `scripts/requirements.py --check`가 45개 요구사항·25개 결정의 schema/원본 일치를 통과했다. R45 변경까지 반영한 루트·문서 안내·제품 Markdown의 로컬 링크 760개에서 없는 대상이나 R/D anchor를 찾지 못했다. |

전체 Python 3.9/3.13 suite, wheel 재빌드·설치, Bun 전체 실행은 코디네이터 소유이며 여기서 중복하지 않았다. 공유 `.venv`와 전역 설치·서비스·물리 기기·모델·PR은 변경하거나 실행하지 않았다.

## 문서 내용과 유지 가능성

45개 ID는 기존 감사 행을 보존한다. 생성 결과는 기능 29개, 비기능 28개로 보이며 12개는 같은 ID의 두 성격을 각각 보여준다. 45개 요구사항에 142개 자동 테스트 연결이 있다. R45의 자동 연결 두 개는 잘못된 증거 분류와 생성 원본 불일치 같은 구조적 오류만 다루고 문구의 의미·사실성은 문서 검토로 남는다고 명시한다. 이는 수용 기준 100% 증명이나 회귀 방지율이 아니다.

설치·CLI·launch와 session 수명·질문 상관관계·successor·프로토콜·개인정보·자원 한도·lease와 복구·slot·색상·입력·증거 경계가 기존 티켓/계약의 R01–R45와 대응한다. 검토한 기준에서 별도의 누락된 제품 요구사항은 확인하지 못했다. 대화 전체 원문을 새로 조사한 작업이 아니므로 보이지 않는 모든 과거 발언까지 빠짐없이 수록했다고 증명하지 않는다.

결정별 사용자 제약·구현 선택·검증 후 정정 분류, 이유·대안·영향·근거와 요구사항 링크는 구현 세부를 사용자 합의로 오인할 위험을 줄인다. D02/R23 정정 후에도 upstream PR, core observer, 모든 UI 관찰, 자동 successor 영구 복구는 현재 약속으로 부활시키면 안 된다.

제품 첫 화면과 문서 탐색표에서 출발해 ID별 수용 기준, 한계, 구현·정확한 테스트로 내려가는 구조는 읽고 수정하기에 적절하다. 긴 문서는 목차와 안정된 anchor로 탐색 가능하다. JSON 원본 두 개에서 네 보기를 생성하고 CI가 byte 일치를 검사하므로 Markdown 수동 복제에 따른 불일치도 감지한다.

비기능 조건에는 2초 heartbeat, 8초 monotonic lease, session/call/frame/ID/client 상한, private permission, backpressure, rollback, Python 3.9 호환성이 있다. 실제 LED 변화의 p95, 장시간 메모리 사용량, USB 재연결 SLO는 합의된 수치가 없다고 maintenance에 명시되어 있으므로 임의의 성능 보장값을 추가하지 않은 것이 맞다.

## CI와 증명 범위

두 workflow는 Python 3.9/3.13의 기존 전체 pytest 실행을 `--verify-tests` 내부에서 유지하며, Bun 설치와 전체 `bun test tests/`, 새 wheel build 및 `GJC_TEST_WHEEL_DIR`을 연결한다. release의 `tag` job은 여전히 `needs: test`이고 Python 3.13 lint 및 별도 release build/metadata 검사는 유지된다. 실제 Ubuntu GitHub Actions 성공 여부는 이 소스 검토로 증명하지 않는다.

검사는 외부의 기존 JUnit을 입력받아 PASS하는 인터페이스가 없고 새 디렉터리에 두 runner를 직접 실행한다. 기존 디렉터리를 거부하고 nonzero 실행을 실패 처리하며, 연결된 pytest 함수의 실행된 모든 parameter와 정확한 Bun 파일/이름을 확인한다. 이는 실수로 오래된 결과를 재사용하는 문제를 막는 장치이며 악의적으로 보고서를 위조하는 테스트 runner에 대한 보안 경계는 아니다.

회귀 오류가 없다고 보장할 수는 없다. 요구사항이나 assertion 자체가 잘못됐거나 조합이 빠진 경우, 실제 GJC·모델·기기·운영체제에서만 드러나는 차이는 이 연결 검사만으로 검출되지 않는다. 기존 실제 GJC fixture 실행과 exact-snapshot replay는 과거 증거이며 현재 문서 검사의 성공을 물리 입력·육안 LED·실제 모델·로그인 서비스·Ubuntu 실행·배포 완료로 확대하지 않는다.

## 최종 핵심 입력 식별

| 파일 | SHA-256 |
|---|---|
| `scripts/requirements.py` | `ecfcb4f474f1966ceb57d9e928c7e1f43f0a38ea89f45b1ff1fe7241ebc30223` |
| `tests/test_requirements_traceability.py` | `50dd1a465b201da7d74ad3071a93d0d36110354352d17bdf91d86b1a8a6822cb` |
| `docs/product/decisions.json` | `4140aa54d0220f6411adb00556a1727e65726ba2a6ef9e5c1a7f739f9546dada` |
| `docs/product/requirements.json` | `1c0b4a1aa70d7352ec2ba807d7cb86beddbabcecdfe431ec3993c7c43ae8b7b4` |
