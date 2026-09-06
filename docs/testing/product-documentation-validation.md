# 제품 문서와 요구사항 연결 검사 검증

**2026-09-06 KST · 로컬 검증 통과.** 의사결정 25개와 요구사항 45개를 정리하고,
새 전체 테스트 결과에 요구사항의 정확한 테스트 참조 142개가 연결되는지 확인했다.
이 보고서는 문서·연결 검사 변경의 증거다. 이전 제품 검증 보고서를 대체하지 않는다.

[제품 문서](../product/README.md) · [변경 절차](../product/maintenance.md) ·
[기계 판독 결과](product-documentation-validation.json) · [독립 리뷰](product-documentation-review.md)

## 무엇을 만들었는가

| 산출물 | 내용 |
|---|---|
| 의사결정 25개 | 최종 선택, 이유, 검토한 대안, 영향·한계, 사용자 합의/구현 선택/검증 후 수정의 구분 |
| 요구사항 45개 | R01–R45 유지, 기능 29개·비기능 28개 보기. 두 성격을 가진 12개는 같은 ID를 공유 |
| 테스트 연결표 | 수용 기준에서 구현 파일, 정확한 테스트, 별도 시나리오와 수동 검증 한계까지 연결 |
| 자동 생성·CI 검사 | JSON 원본과 Markdown 일치, 새 pytest/Bun 결과의 정확한 파일·이름·통과 여부 확인 |
| 연결 검사 회귀 테스트 16개 | 잘못된 ID/경로/선언/증거 분류, 문서 불일치, 실패·skip·다른 파일·이전 보고서·실행 입력 변경 거부 |

45개 모두 자동 테스트 참조를 갖는다. **이는 모든 수용 기준의 증명률이 아니다.**
예를 들어 R45의 자동 테스트는 구조와 생성 문서 일치를 검사한다. 문장이 실제 제품 동작과 맞는지,
실험 결과를 과장하지 않는지는 별도 의미 검토가 필요하다.

## 새로 실행한 결과

| 환경 | Python | Bun | 요구사항 연결 | 실패·skip |
|---|---:|---:|---:|---:|
| macOS · Python 3.13.5 | 472 통과 | 44 통과 | pytest 116 + Bun 26 통과 | 0 |
| macOS · Python 3.9.6 | 472 통과 | 44 통과 | pytest 116 + Bun 26 통과 | 0 |

새 wheel을 빌드한 뒤 각 환경에서 다음 명령을 실행했다. 각 실행은 새 보고서 디렉터리,
분리된 HOME과 wheel 설치 통합 테스트를 사용했다. pytest suite 기록 시간은 각각 20.299초,
33.881초이며 물리 입력·LED 지연 측정값이 아니다.

```sh
GJC_TEST_WHEEL_DIR=/tmp/gjc-docs-run/wheel <검증 환경>/bin/python scripts/requirements.py --verify-tests --report-dir <새 보고서 디렉터리>
```

실제 사용한 Python 경로와 전체 명령은 아래 실행 영수증에 보존했다.

| 실행 | 영수증 | 개별 테스트 결과 |
|---|---|---|
| Python 3.13 | [result.json](product-documentation-evidence/final-py313/result.json) | [pytest.xml](product-documentation-evidence/final-py313/pytest.xml) · [bun.xml](product-documentation-evidence/final-py313/bun.xml) |
| Python 3.9 | [result.json](product-documentation-evidence/final-py39/result.json) | [pytest.xml](product-documentation-evidence/final-py39/pytest.xml) · [bun.xml](product-documentation-evidence/final-py39/bun.xml) |

각 영수증은 실행 입력 92개 파일의 SHA-256을 포함한다. 두 실행에서 검증 전후와 기록 시점의
입력이 같았다. 보존한 XML은 hostname 속성만 제거했고, testcase 이름·결과는 유지했다.
원본 XML과 보존본의 해시 및 새 wheel 해시는 기계 판독 결과에 기록했다.

전체 Ruff, 두 workflow의 actionlint, `git diff --check`, 생성 문서 일치 검사도 통과했다.
PR 테스트와 publish 전 테스트 workflow에 같은 연결 검사를 적용했지만 실제 GitHub Actions는
이번 작업에서 실행하지 않았다.

## 검토에서 찾아 수정한 문제

| 문제 | 수정과 재검증 |
|---|---|
| 실행하는 실험 helper가 입력 해시에서 빠짐 | 실제 테스트가 가져오는 experiments의 Python/TypeScript를 포함하고 과거 evidence 파일은 제외 |
| pytest parameter ID 안의 `::`를 클래스 구분자로 처리 | parameter 이전의 테스트 식별자만 분리하고 정확한 사례 이름을 보존 |
| 현행 native hook 선택이 “대체됨”으로 표시 | 현재 결정은 채택으로 수정하고 폐기된 대안을 본문에서 구분 |
| successor 실험의 특정 응답·필드가 제품 필수 요구로 들어감 | 공통 수용 기준은 명시적 checkpoint/답변 전달로 정리하고 실험 절차는 검증 근거로 이동 |

첫 두 문제는 [수정 전 실패 기록](product-documentation-evidence/gate-review-red.txt)을 보존했다.
수정 후 새 연결 검사 테스트 16개가 통과했고, 양쪽 전체 실행에도 포함됐다.

## 현재 증거의 경계

이전 [제품 소스 고정 기록](final-product-hashes.json)의 29개 파일은 변경되지 않았다.
기존 [2차 감사](gjc-second-audit.md)의 456개 Python·44개 Bun 및 실제 GJC 시나리오 결과는
당시 실행 증거로 유지한다. 이번 Python 수가 472개인 것은 연결 검사 테스트 16개가 추가됐기 때문이다.

이번 실행은 단위·통합 테스트와 문서 연결 검사다. 실제 GJC 터미널 시나리오를 다시 실행하거나,
물리 키·LED, 실제 모델의 지침 준수, 전역 hook/로그인 서비스, Ubuntu 실행을 확인한 결과가 아니다.
커밋·PR·릴리스도 수행하지 않았다.

**회귀 오류 0개는 보장하지 않는다.** 잘못된 요구사항, 약한 assertion, 빠진 조합과 실제 환경의
차이는 별도로 검토해야 한다. 이 변경은 요구사항·테스트·실행 증거가 서로 어긋나는 실수를 자동으로
발견하고, 사람이 검토할 나머지 범위를 명확히 하는 장치다.
