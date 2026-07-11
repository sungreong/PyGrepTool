# Python Search Dependency Recommendations

조사일: 2026-07-08

목표는 Python 코드 안에서 사용할 검색 구현을 고르는 것이다. 중요한 기준은 설치 부담이 작고, Windows/macOS/Linux에서 예측 가능하게 동작하며, LLM tool 결과를 안정적으로 만들 수 있는지다.

## 결론

현재 프로젝트에는 다음 조합이 가장 좋다.

```text
기본값: stdlib Python backend + optional ripgrep subprocess
추가해도 좋은 가벼운 의존성: pathspec
무거워서 기본 의존성에서 제외: tree-sitter, ast-grep, hyperscan, RE2, pyahocorasick
```

추천 정책:

1. 패키지 기본 설치는 계속 무의존성으로 유지한다.
2. `rg`가 있으면 큰 코드베이스 검색에 사용한다.
3. 단일 파일/작은 디렉터리/반복 호출은 Python backend를 사용한다.
4. `.gitignore` 호환은 `pathspec` optional extra로 제공한다.
5. AST/구조 검색은 별도 extra 또는 별도 tool로 분리한다.

## 후보 비교

| 후보 | Python 내 사용 방식 | 설치 부담 | 장점 | 제한 | 판정 |
| --- | --- | --- | --- | --- | --- |
| Python stdlib (`os.walk`, `fnmatch`, `re`) | 직접 import | 없음 | 설치 실패가 없고 테스트가 쉽다 | 대형 repo에서는 `rg`보다 느릴 수 있음, `.gitignore` 직접 구현 필요 | 기본 유지 |
| `ripgrep` subprocess | `subprocess.run(["rg", ...])` | Python 패키지는 아니고 실행 파일 필요 | 빠름, ignore/hidden/binary 정책 우수, JSON 출력 지원 | 사용 환경에 `rg` 설치 필요 | optional backend 유지 |
| `pathspec` | Python 패키지 | 작음, pure Python 계열 | `.gitignore`/Git wildmatch 처리에 적합 | 검색 엔진은 아니고 경로 필터만 담당 | optional extra로 지원 |
| `regex` | `re` 대체 import | 보통, CPython 중심 | `re`보다 기능이 많음 | PyPy 제한, 검색 엔진 전체 속도 문제를 해결하진 않음 | 기본 제외 |
| `tree-sitter` + grammars | Python binding + 언어 grammar | 중간 이상 | AST 단위 구조 검색 가능 | 언어별 grammar 관리 필요, 텍스트 grep과 목적이 다름 | 별도 extra 후보 |
| `ast-grep` | 보통 CLI 또는 별도 도구 | 실행 파일/도구 필요 | 구조 검색/리라이트에 강함 | 일반 텍스트 검색 backend로는 과함 | 별도 tool 후보 |
| `pyahocorasick` | C extension | C extension/wheel 의존 | 다중 고정 문자열 검색에 빠름 | regex 검색에는 맞지 않음, 설치 실패 가능성 | 기본 제외 |
| `hyperscan` | C extension wheel | 큼 | 대규모 다중 regex에 강함 | wheel이 크고 엔진/PCRE/Boost 등을 포함 | 제외 |
| `google-re2` | C++ binding | 큼/플랫폼 제약 | 안전한 regex 엔진 | 시스템 RE2/pybind11 요구 가능, Python `re`와 문법 차이 | 제외 |

## 왜 `pathspec`만 추가 후보인가

`pathspec`은 검색 엔진이 아니라 경로 필터링 라이브러리다. 즉 현재 Python backend 구조를 거의 유지하면서 `.gitignore` 호환만 개선할 수 있다.

현재 Python backend:

```text
roots -> os.walk -> 수동 skip dir -> fnmatch include -> re.finditer
```

`pathspec` 설치 후 구조:

```text
roots -> os.walk -> pathspec ignore filter -> include/exclude -> re.finditer
```

설치 부담 대비 개선 효과가 가장 크다. 반면 `tree-sitter`, `hyperscan`, `RE2`는 성격이 좋아도 기본 패키지 의존성으로 넣기에는 무겁다.

## 추천 API 정책

### 지금 유지할 기본값

```python
search("TODO", "src", backend="auto")
```

`auto`는 기존처럼 `rg -> grep -> python` 순서가 좋다. 큰 코드베이스에서는 이 선택이 자연스럽다.

### Python 내부 반복 호출 최적화

작은 범위를 여러 번 검색할 때는 명시적으로 Python backend를 쓰는 편이 낫다.

```python
search("TODO", "src/pygreptool/tool.py", regex=False, backend="python")
```

현재 실측에서도 작은 예제에서는 Python backend가 외부 `rg` 호출보다 훨씬 빠르다. 이유는 `rg` 자체가 느린 것이 아니라, 매 호출마다 외부 프로세스를 띄우는 비용이 있기 때문이다.

### 작은 범위 자동 최적화

`smart` backend를 제공한다.

```text
single file 또는 작은 root -> python
큰 directory -> rg
rg 없음 -> python
```

단순한 휴리스틱으로 후보 파일 수가 작으면 Python backend를 쓰고, 기준을 넘으면 외부 검색 backend로 넘어간다.

## 기본 의존성에서 제외할 후보

### `tree-sitter`

AST 검색이 필요하면 좋은 선택이다. 다만 텍스트 검색과는 목적이 다르고, Python/JavaScript/TypeScript 등 언어별 grammar를 함께 관리해야 한다. 기본 검색 도구에 넣으면 패키지 성격이 커진다.

### `hyperscan`

성능은 강력하지만 wheel이 크고 내부에 스캔 엔진, PCRE, Boost 등을 포함한다. “의존성이 적어야 한다”는 현재 기준에는 맞지 않는다.

### `google-re2`

안전한 regex 엔진이라는 장점은 있지만, 빌드/플랫폼 제약이 있고 Python `re`와 문법 차이가 생긴다. 기본 backend로 넣으면 사용자 기대와 달라질 수 있다.

### `pyahocorasick`

고정 문자열 여러 개를 한 번에 찾는 용도라면 좋다. 하지만 이 프로젝트는 regex와 line/column 결과 정규화가 핵심이라 기본 엔진으로는 범용성이 부족하다.

## 최종 추천

지금 당장 바꾼다면 코드 방향은 이렇다.

```text
1순위: 현재 구조 유지
2순위: optional dependency로 pathspec 유지
3순위: backend="smart" 유지
4순위: AST 검색은 별도 tool로 분리
```

`requirements.txt` 기본값은 그대로 두고, 나중에 필요하면 extra dependency만 추가하는 편이 좋다.

```toml
[project.optional-dependencies]
ignore = ["pathspec>=0.12,<1.1"]
```

## 참고 링크

- Python `re`: https://docs.python.org/3/library/re.html
- `ripgrep`: https://github.com/BurntSushi/ripgrep
- `pathspec`: https://github.com/cpburnz/python-pathspec
- `regex`: https://pypi.org/project/regex/
- `tree-sitter`: https://pypi.org/project/tree-sitter/
- `pyahocorasick`: https://pyahocorasick.readthedocs.io/
- `hyperscan`: https://python-hyperscan.readthedocs.io/
- `google-re2`: https://pypi.org/project/google-re2/
