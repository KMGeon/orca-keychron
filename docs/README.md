# 문서 안내

현재 제품의 선택과 요구사항은 **[제품 문서](product/README.md)**에서 시작한다.
구현을 변경할 때에는 그 문서의 요구사항 ID와 테스트 연결을 함께 갱신한다.

문서·연결 검사의 최신 로컬 검증은 [2026-09-06 검증 기록](testing/product-documentation-validation.md)에
있다. 기존 제품 감사와 별도로 새 실행 결과와 미실행 범위를 보존한다.

| 문서 종류 | 역할 | 읽는 기준 |
|---|---|---|
| [제품 문서](product/README.md) | 의사결정·기능/비기능 요구사항·테스트 연결·변경 절차 | 현재 편집 기준. 상세 보기는 JSON 원본에서 생성 |
| [사용자 가이드](gjc-guide.md) | 설치, 명령, 사용, 지원 범위 | 사용자 동작의 설명 |
| [개발 티켓](gjc-keychron-development-ticket.md)·[bridge 계약](gjc-bridge-contract.md)·[패키지 구조](gjc-package-layout.md) | 합의된 개발 범위와 기술 계약 | 새 요구사항과 충돌하면 이유와 수정 범위를 함께 검토 |
| [설계 조사](gjc-observation-design.md)·[훅 실험](gjc-hook-experiment-results.md) | 검토한 대안, 반증된 가정, 실험 과정 | 당시 제안·버전·미실행 문구를 현재 기능으로 읽지 않음 |
| [2차 검증](testing/gjc-second-audit.md)·[요구사항 감사](testing/gjc-requirements-matrix.md)·[하드웨어 기록](gjc-hardware-validation.md) | 특정 소스와 환경에서 실행한 증거 | 날짜·해시·검증 경계를 보존하는 과거 기록 |

제품 문서는 기존 결정을 재구성한 현재 탐색 창구이고, 감사·실험 파일은 근거다.
새 변경이 생겨도 예전 PASS 기록이나 원래 조사 결과를 새 결과로 고쳐 쓰지 않는다.
새 검증은 새 기록으로 남긴다.
