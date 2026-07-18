# PyGrepTool 탐색 평가: 정확도, 호출 수, 지연 시간

> 기준 실행일: 2026-07-18 · Windows 로컬 환경 · 각 측정은 1회 warm-up 뒤 7회 중앙값

## 한 줄 결론

PyGrepTool은 `rg`보다 빠른 문자열 검색기나 CodeGraph의 대체 call graph가 아니다. 실제 sandbox 또는 제한된 workspace 안에서 agent가 **허용된 파일만**, **파일·줄 근거와 함께**, **필요한 만큼만** 탐색하도록 만드는 read-only navigation layer다.

이번 평가에서 6개의 대표 탐색 질문은 모두 해결됐고, 총 8회의 tool 호출이 필요했다. 평균은 질문당 **1.33회**였으며, 설명을 위해 주변 근거가 필요한 질문만 2회 호출했다.

## 평가 범위

평가 fixture는 다음 정책을 사용한다.

```json
{
  "allowed_roots": ["src", "docs"],
  "policy": { "deny_globs": ["private/**"] }
}
```

따라서 agent는 가상 경로 `/src`, `/docs`만 읽을 수 있다. `private/credential.py`는 비교용 무해한 marker를 포함하지만, PyGrepTool에는 노출되지 않아야 한다.

### 단일 요청 골든셋

| 검증 | 기대 결과 | 상태 |
| --- | --- | --- |
| service Python 파일 찾기 | `/src/alpha_service.py`, `/src/beta_service.py` | 통과 |
| backend 설정 위치 찾기 | `/src/alpha_service.py:1`의 `BACKEND_MODE = "smart"` | 통과 |
| beta marker 문맥 읽기 | 함수 선언과 `BETA_EXACT_NEEDLE` 반환 값 | 통과 |
| private token 탐색 | `ToolInputError`로 정책 차단 | 통과 |

결과: **4 / 4 통과**

### 실제 질문형 탐색 여정

| 질문 | 기준 도구 흐름 | 호출 수 | 결과 |
| --- | --- | ---: | --- |
| `src`의 service Python 파일 찾기 | `find_files` | 1 | 통과 |
| smart backend 설정의 근거 찾기 | `search_code` | 1 | 통과 |
| beta marker의 반환 값 설명 | `search_code → read_context` | 2 | 통과 |
| alpha report TODO와 다음 동작 설명 | `search_code → read_context` | 2 | 통과 |
| operations runbook 찾기 | `find_files` | 1 | 통과 |
| private token 요청 | `search_code` → 정책 차단 | 1 | 통과 |

결과: **6 / 6 통과, 총 8회, 평균 1.33회 호출**

`search_code → read_context`는 불필요한 전체 파일 읽기를 피하면서도 답변에 필요한 주변 근거를 확보하는 2단계 흐름이다. 반대로 파일명·확장자·정확한 설정 키가 이미 질문에 포함되면 한 번의 호출로 끝낸다.

> [!NOTE]
> 위 호출 수는 정책을 지키는 기준 계획이다. 특정 LLM이 실제로 같은 도구를 같은 횟수로 선택한다는 뜻은 아니다. 모델별 tool selection 품질은 별도 live-agent 평가로 측정해야 한다.

## 지연 시간 결과

### 질문을 해결하는 데 걸린 시간

| 방식 | 질문 유형 | 중앙값 |
| --- | --- | ---: |
| PyGrepTool in-process | 1회 호출 여정 | 6.16–63.06 ms |
| PyGrepTool in-process | 근거를 읽는 2회 호출 여정 | 89.51–105.29 ms |
| PyGrepSkill command | 1회 호출 여정 | 241.76–665.46 ms |
| PyGrepSkill command | 2회 호출 여정 | 631.60–655.38 ms |
| `rg` | 정확한 문자열 `BETA_EXACT_NEEDLE` 검색 | 36.75 ms |
| CodeGraph | 인덱스 후 심볼 질의 | 594.92 ms |
| CodeGraph | 인덱스 후 호출자 질의 | 651.21 ms |

`in-process`는 LangChain의 `create_pygrep_tools()`처럼 실행 중인 Python 프로세스에 tool을 붙이는 방식이다. `PyGrepSkill command`는 매 tool 호출마다 `invoke_pygreptool.py`를 새 Python 프로세스로 실행하는 이식 가능한 방식이다. 후자는 설치·복사에는 편하지만 프로세스 시작 비용이 크다.

**실제 agent 애플리케이션에는 in-process toolkit을 권장한다.** Skill은 agent에게 올바른 도구 선택과 policy-bound runner 사용법을 알려 주는 배포 단위로 쓰는 것이 적합하다.

## `rg`, CodeGraph, PyGrepTool의 역할 분리

| 질문 | 가장 적합한 선택 | 이유 |
| --- | --- | --- |
| 신뢰된 checkout에서 정확한 텍스트를 최대한 빨리 찾기 | `rg` | 최소한의 검색 오버헤드로 문자열·정규식을 찾는다. |
| 심볼, 호출자/피호출자, 영향 범위를 찾기 | CodeGraph | 사전 인덱스로 코드 관계를 질의한다. |
| agent가 제한된 workspace에서 파일·문자열·문맥을 근거와 함께 탐색하기 | PyGrepTool | virtual path, `allowed_roots`, deny/redaction policy, 구조화 결과를 함께 제공한다. |

이번 fixture에서 CodeGraph는 `beta_marker`의 호출자인 `build_alpha_report`를 찾았다. 이것은 PyGrepTool이 의도적으로 제공하지 않는 semantic graph 기능이다. 반면 비교용 private marker는 raw `rg`와 CodeGraph index에서 볼 수 있었지만, PyGrepTool은 trusted `allowed_roots` 밖이라는 이유로 요청 자체를 거절했다.

이는 CodeGraph가 안전하지 않다는 일반적 결론이 아니다. CodeGraph의 인덱스 범위와 secret 처리 역시 sandbox, mount, ignore, 접근 제어 정책으로 별도 설계해야 한다는 뜻이다.

## 재현 방법

```powershell
# 기본: PyGrepTool golden set, 호출 수, rg 기준선
python scripts\evaluate_navigation.py --iterations 7

# CodeGraph가 설치되어 있으면 심볼/호출자 질의도 추가
# 필요한 경우 fixture 안에 로컬 .codegraph index를 생성하며 Git은 이를 무시한다.
python scripts\evaluate_navigation.py --iterations 7 --with-codegraph

# 골든셋 회귀 테스트만 실행
python -m pytest tests\test_navigation_golden_set.py -q

# 전체 회귀 테스트
python -m pytest
```

평가 정의는 [`tests/fixtures/navigation_golden_set.json`](../tests/fixtures/navigation_golden_set.json)에 있고, 실행기와 호출 수 집계 로직은 [`scripts/evaluate_navigation.py`](../scripts/evaluate_navigation.py)에 있다.

## 현재 한계와 다음 단계

- 현재 골든셋은 핵심 행동을 고정한 **작은 deterministic suite**다. 공개 성능 주장의 근거로는 실제 프로젝트 질문 20–30개 이상으로 늘리는 것이 적절하다.
- 이 문서는 기준 tool plan의 호출 수를 측정한다. `gpt-4o-mini` 같은 실제 모델에 같은 질문을 던져 **정답률, 정책 위반률, 평균 tool 호출 수, 불필요한 호출 수**를 측정하면 모델 선택 품질까지 평가할 수 있다.
- CodeGraph와의 비교는 공통 질문에서 속도 순위를 매기기보다, 텍스트 탐색·semantic graph·policy-scoped navigation의 역할을 분리해야 공정하다.

## 프로젝트 포지션

PyGrepTool의 가치는 “grep을 더 빠르게 만든 것”이 아니다. agent가 실제 격리 환경 안에서 코드를 탐색할 때, 최소 권한과 줄 단위 근거를 유지하면서 필요한 만큼만 읽도록 만든다는 점에 있다.
