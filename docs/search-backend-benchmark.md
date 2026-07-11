---
title: "Search Backend Benchmark"
theme: report
intent: reference
toc: true
---

# Search Backend Benchmark

이 문서는 `pygreptool`의 검색 backend를 현재 저장소와 현재 실행 환경에서 비교한 결과를 정리한다. 목적은 LLM tool이나 agent loop 전체가 아니라 raw `search()` 호출의 검색 속도만 비교하는 것이다.

## 측정 대상

- 함수: `pygreptool.search()`
- backend: `python`, `rg`, `smart`, `auto`, `grep`
- 반복 횟수: backend별 9회
- 대표값: median ms
- 환경: Windows
- 실행 파일 상태: `rg` 설치됨, `grep` 미설치

측정 명령:

```powershell
python scripts\benchmark_search_backends.py `
  --repeats 9 `
  --format json
```

## 케이스 설계

| 케이스 | pattern | roots | include | 후보 파일 수 |
| --- | --- | --- | --- | ---: |
| `single_file_symbol` | `search_code` | `src/pygreptool/tool.py` | 없음 | 1 |
| `docs_optional_dependency` | `pathspec` | `docs` | `*.md` | 5 |
| `src_regex_functions` | `def search_with_` | `src` | `*.py` | 12 |
| `repo_backend_keyword` | `backend` | `src`, `tests`, `docs`, `examples` | `*.py`, `*.md` | 34 |
{: .zebra .bordered .compact .table-fit caption="작은 범위, 문서 범위, src 범위, 저장소 범위를 각각 대표하도록 잡았다"}

## 요약

| 케이스 | winner | median ms | 2위 | 관찰 |
| --- | --- | ---: | --- | --- |
| `single_file_symbol` | `python` | 1.092 | `smart` 1.104 | 단일 파일에서는 Python이 사실상 최선 |
| `docs_optional_dependency` | `smart` | 6.280 | `python` 9.839 | `smart`가 Python 경로를 선택해 가장 빨랐음 |
| `src_regex_functions` | `python` | 10.192 | `smart` 12.329 | 12개 파일 범위에서도 Python 우세 |
| `repo_backend_keyword` | `python` | 32.542 | `smart` 35.844 | 34개 파일 범위까지도 Python이 가장 빨랐음 |
{: .zebra .bordered .compact .table-fit caption="현재 저장소와 환경에서는 Python 기반 경로가 전 케이스에서 가장 유리했다"}

## 상세 결과

### 1. `single_file_symbol`

- `python`: 후보 1개, 매칭 파일 1개, 총 4 match, median `1.092ms`
- `smart`: 후보 1개, 매칭 파일 1개, 총 4 match, median `1.104ms`
- `auto`: 후보 1개, 매칭 파일 1개, 총 4 match, median `35.127ms`
- `rg`: 후보 1개, 매칭 파일 1개, 총 4 match, median `41.609ms`
- `grep`: 현재 환경에서 미설치

해석:
단일 파일에서는 `python`과 `smart`가 사실상 동률이고, 외부 프로세스를 띄우는 `auto`와 `rg`는 훨씬 느렸다.

### 2. `docs_optional_dependency`

- `smart`: 후보 5개, 매칭 파일 5개, 총 21 match, median `6.280ms`
- `python`: 후보 5개, 매칭 파일 5개, 총 21 match, median `9.839ms`
- `auto`: 후보 5개, 매칭 파일 5개, 총 21 match, median `53.798ms`
- `rg`: 후보 5개, 매칭 파일 5개, 총 21 match, median `53.914ms`
- `grep`: 현재 환경에서 미설치

해석:
문서 5개 범위에서는 `smart`가 Python 경로를 타며 가장 빨랐다.

### 3. `src_regex_functions`

- `python`: 후보 12개, 매칭 파일 3개, 총 3 match, median `10.192ms`
- `smart`: 후보 12개, 매칭 파일 3개, 총 3 match, median `12.329ms`
- `auto`: 후보 12개, 매칭 파일 3개, 총 3 match, median `49.942ms`
- `rg`: 후보 12개, 매칭 파일 3개, 총 3 match, median `50.252ms`
- `grep`: 현재 환경에서 미설치

해석:
`src` 범위의 regex search에서도 `python`이 가장 빨랐고, `smart`가 그 뒤를 이었다.

### 4. `repo_backend_keyword`

- `python`: 후보 34개, 매칭 파일 27개, 총 233 match, median `32.542ms`
- `smart`: 후보 34개, 매칭 파일 27개, 총 233 match, median `35.844ms`
- `auto`: 후보 34개, 매칭 파일 27개, 총 233 match, median `60.377ms`
- `rg`: 후보 34개, 매칭 파일 27개, 총 233 match, median `65.096ms`
- `grep`: 현재 환경에서 미설치

해석:
이 저장소 전체 범위에서도 `python`이 가장 빨랐고, `smart`가 아주 근접하게 따라왔다.

## 해석

이 결과만 보면 현재 저장소에서는 `python`이 가장 빠르고, 기본값으로는 `smart`가 가장 실용적이다.

이유는 단순하다.

- 후보 파일 수가 많지 않다.
- Windows에서 외부 프로세스를 띄우는 비용이 무시되지 않는다.
- `smart`는 작은 범위를 Python으로 보내기 때문에 거의 최적에 가깝다.
- `auto`는 `rg`를 먼저 타므로 현재 저장소 크기에서는 오히려 불리하다.

하지만 이 결과를 일반화하면 안 된다.

- 더 큰 monorepo
- 수백~수천 파일 범위
- ignore 처리와 병렬화 이점이 더 커지는 환경

이런 조건에서는 `rg`가 다시 유리해질 수 있다. 따라서 이 benchmark는 “현재 저장소에서의 기본값 판단 자료”로 읽는 것이 맞다.

## 결론

- 현재 저장소 기준 최선의 기본값: `smart`
- 검색 속도 자체만 보면 가장 빠른 경로: `python`
- `auto`는 `rg` 우선 정책 때문에 현재 repo 규모에서는 손해
- `grep`은 이 환경에서 비교 불가

블로그용 설명에는 이 benchmark를 넣고, 운영 기본값 설명에는 `smart`를 추천하는 근거로 사용하면 자연스럽다.
