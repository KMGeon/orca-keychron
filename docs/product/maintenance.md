# 변경과 회귀 방지 절차

[제품 문서 처음으로](README.md)

**의사결정 → 요구사항 → 수용 기준 → 테스트 → 실행 증거**를 한 변경에서 함께 관리한다.
연결표가 있다는 사실과 테스트가 올바른 동작을 검증한다는 사실은 구분한다.

## 변경 한 건의 작업 순서

1. 관련 `Rxx`를 찾는다. 동작의 의미가 바뀌면 `decisions.json`에 이유와 대안을 남긴다. 기존 ID를 다른 의미에 재사용하지 않는다. 새 요구사항은 `R46`부터 추가할 수 있다.
2. `requirements.json`의 동작·수용 기준·한계를 수정하고 실제 테스트를 추가하거나 보강한다. 버그 수정은 가능한 경우 수정 전 실패와 수정 후 통과를 확인한다.
3. `python scripts/requirements.py --write`로 네 개 문서를 생성한다. 생성된 Markdown을 직접 고치지 않는다. 이어서 `--check`로 구조와 원본 일치를 확인한다.
4. 새 wheel을 준비하고 `GJC_TEST_WHEEL_DIR=... python scripts/requirements.py --verify-tests`를 실행한다. 연결된 테스트가 실제로 통과했는지 확인한다.
5. 변경이 닿은 실제 환경을 추가 검증한다. 버전·훅·상태 전달은 실제 GJC, 입력·HID는 실제 기기, 서비스는 실제 로그인 환경이 필요할 수 있다. 미실행 범위는 기록하고 리뷰에서 판단한다.

폐기·대체도 의사결정이다. 기존 요구사항을 조용히 삭제하거나, 실패하는 테스트의 연결을 지워 검사를
통과시키지 않는다. 요구 자체의 폐기가 필요하면 이전 ID와 근거를 보존하고 검사 정책 변경까지 함께 검토한다.

## 한 번 준비할 개발 환경

Python 3.9 이상과 Bun이 필요하다. 기존 작업 환경을 바꾸지 않으려면 전용 가상환경을 사용한다.
아래 명령은 저장소 루트에서 실행한다. 출력 wheel 디렉터리는 이전 산출물이 섞이지 않는 새 경로를 선택한다.

```sh
uv venv /tmp/orca-keychron-requirements-dev
uv pip install --python /tmp/orca-keychron-requirements-dev/bin/python '.[dev]' build
/tmp/orca-keychron-requirements-dev/bin/python -m build --wheel --outdir /tmp/gjc-requirements-wheel
GJC_TEST_WHEEL_DIR=/tmp/gjc-requirements-wheel /tmp/orca-keychron-requirements-dev/bin/python scripts/requirements.py --verify-tests
```

검사는 저장소의 기존 Python·Bun 테스트를 실행한다. GJC 터미널 시나리오, 전역 hook/서비스 설치,
모델 호출, 물리 키 입력은 이 명령이 실행하지 않는다. 로컬 검증 결과 경로는 완료 시 출력한다.
CI에서는 Python 3.9와 3.13 각각 같은 검사를 실행한다.

## 세 가지 검사 명령의 차이

| 명령 | 확인하거나 변경하는 것 | 증명하지 않는 것 |
|---|---|---|
| `python scripts/requirements.py --write` | JSON 원본에서 네 개 Markdown 보기를 갱신 | 테스트 실행·통과 |
| `python scripts/requirements.py --check` | ID, 연결 경로, Python 선언, 분류, 생성 문서 일치 | Bun 실행 이름, 실제 assertion, 실제 환경 |
| `python scripts/requirements.py --verify-tests` | 구조 검사 후 새 pytest/Bun 실행 결과에 정확한 테스트가 존재하고 통과하는지 확인 | 모든 수용 기준·경계 조합의 완전성, 실제 GJC·모델·물리 기기 |

`--verify-tests`는 새 보고서 디렉터리만 사용하고 실행 전후 입력 파일의 해시를 비교한다.
기존 성공 보고서를 다시 읽어 현재 코드가 통과했다고 판단하지 않는다. 연결한 parameterized Python
함수는 보고서에 나온 해당 함수의 모든 사례가 통과해야 한다. Bun은 파일과 실행된 전체 이름을 맞춘다.
실패뿐 아니라 skip도 연결 검사를 통과시키지 못한다.

결과를 지정한 곳에 보존하려면 아직 존재하지 않는 디렉터리를 전달한다.

```sh
GJC_TEST_WHEEL_DIR=/tmp/gjc-requirements-wheel python scripts/requirements.py --verify-tests --report-dir /tmp/gjc-requirements-check-001
```

`result.json`에는 실행 명령, 입력 해시, 테스트 수와 연결 검사 결과가 있다.
`pytest.xml`과 `bun.xml`에는 새 실행의 결과가 있다. 저장소에 증거를 추가할 때에는 비밀값·질문 내용·환경 정보가
포함됐는지 먼저 확인하고, 과거 검증 파일을 덮어쓰지 않는다.

## 연결을 추가하는 예

기존 R39의 사람 호출 우선순위를 보강한다면 `verification`에 정확한 사례를 연결한다.
한 파일 전체를 연결한 것만으로 모든 동작이 검증됐다고 표시하지 않는다.

```json
{
  "kind": "pytest",
  "target": "tests/test_gjc_state_invariants.py",
  "selector": "test_all_priority_subsets_and_order_permutations_match_independent_oracle",
  "layer": "unit",
  "note": "독립 기대값으로 우선순위 순열을 검사한다. 물리 LED 확인은 포함하지 않는다."
}
```

`kind`는 실행 방식, `layer`는 검증 수준이다. `pytest`/`bun`은 단위 또는 통합으로만 표시한다.
실제 GJC 실행 파일은 `scenario`, 실제 기기 확인은 `manual`, 설명·지원 범위 검토는 `document`로 연결하고
필요 환경과 미검증 범위를 `note`에 쓴다. 모의 이벤트 테스트를 `hardware` 증거로 표시하면 구조 검사에서 거부한다.

## 리뷰에서 확인할 질문

1. 수용 기준의 기대값을 제품 코드의 상수·함수에서 그대로 가져와 자기 자신을 검증하고 있지는 않은가?
2. 정상 사례뿐 아니라 반대 사례도 실패하는가? 예: 작업 10개가 질문 1개를 덮거나, 한 답변이 두 질문을 지우면 실패해야 한다.
3. 시간과 실행 ID가 맞는가? 답변 전 기록을 답변 후 결과로 쓰거나 다른 launch의 색을 재사용하면 안 된다.
4. 테스트 연결이나 parameter를 지워 통과시킨 것은 아닌가? 바뀐 기능의 의미와 지원 범위가 함께 검토됐는가?
5. 실제 모델·키보드·서비스에서만 확인할 수 있는 부분을 자동 테스트 통과로 대신하지 않았는가?

## 아직 별도로 관리할 품질 목표

현재 2초 heartbeat, 8초 lease, 프레임·세션 상한은 계약의 수치다. 이벤트 발생부터 실제 LED 변화까지의
p95 지연, 장시간 메모리 사용량, USB 재연결 시간에 대한 합의된 SLO는 없다.
추가할 때에는 측정 환경·입력 부하·허용값·반복 횟수를 요구사항에 먼저 기록하고 측정 테스트를 연결한다.
연결표가 있다고 해서 측정하지 않은 수치를 보장값으로 채우지 않는다.
