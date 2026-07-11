# Open Source References

조사일: 2026-07-08

이 문서는 `pygreptool`과 비슷한 문제를 다루는 오픈소스를 정리한다. 현재 구현은 특정 프로젝트의 내부 코드를 포팅한 것이 아니라, 외부 검색 도구(`rg`, `grep`)를 호출하고 순수 Python fallback(`os.walk`, `fnmatch`, `re`)을 제공하는 얇은 adapter 방식이다.

## 현재 구현과의 관계

- `rg` backend는 `ripgrep` 실행 파일의 JSON 출력(`rg --json`)을 파싱한다.
- `grep` backend는 GNU/BSD 계열 `grep` CLI 출력 형식을 정규화한다.
- `python` backend는 Python 표준 라이브러리만 사용한다. 디렉터리는 `os.walk()`로 순회하고, glob 필터는 `fnmatch`, 패턴 검색은 `re.finditer()`로 처리한다.
- 이 프로젝트의 목표는 검색 엔진을 새로 만드는 것이 아니라, 검색 결과를 `SearchResult`와 LLM tool JSON으로 안정적으로 표준화하는 것이다.

## 텍스트 검색 도구

| 프로젝트 | 성격 | 참고할 점 | `pygreptool` 적용 상태 |
| --- | --- | --- | --- |
| `ripgrep` | Rust 기반 고성능 line-oriented 검색 도구 | gitignore 존중, 숨김/바이너리 기본 제외, Windows/macOS/Linux 지원, JSON 출력 | 현재 `rg` backend로 직접 사용 |
| GNU `grep` | 표준에 가까운 범용 텍스트 검색 도구 | 재귀 검색, include/exclude, fixed string/regex 모드 | 현재 `grep` backend로 지원하되 Windows에는 없을 수 있음 |
| `ack` | 프로그래머용 grep 대안 | 코드 검색에 맞춘 파일 타입/ignore 정책, 휴대성 | 직접 backend 없음. UX 참고 대상 |
| The Silver Searcher (`ag`) | `ack` 계열의 빠른 코드 검색 도구 | ignore 파일 활용, 코드 검색 성능 최적화 | 직접 backend 없음. future backend 후보 |
| `ugrep` | grep 호환을 지향하는 고기능 검색 도구 | boolean query, fuzzy search, 압축/문서 파일 검색, TUI | 범위가 넓어 현재 목표 밖. 고급 검색 아이디어 참고 |

## 구조 검색/리팩터링 도구

| 프로젝트 | 성격 | 참고할 점 | `pygreptool`과의 거리 |
| --- | --- | --- | --- |
| `ast-grep` | AST 기반 구조 검색, lint, rewrite 도구 | 텍스트가 아니라 syntax tree 단위로 검색한다. 함수/클래스/호출 구조 검색에 적합 | 현재 `pygreptool`은 텍스트 검색 도구라 직접 대체 관계는 아님 |
| `comby` | 구조적 search/replace 도구 | 여러 언어에서 템플릿 기반 구조 검색과 변경 지원 | 검색 결과 표준화 이후 rewrite 기능을 확장할 때 참고 가능 |

## 구현 관점에서 배운 점

### 1. 작은 범위와 큰 범위의 최적 backend가 다르다

작은 파일/폴더에서는 외부 프로세스 실행 비용 때문에 Python fallback이 더 빠를 수 있다. 큰 코드베이스에서는 `ripgrep`처럼 병렬화와 ignore 처리에 최적화된 도구가 유리하다.

현재 정책:

```text
auto -> rg -> grep -> python
```

구현된 개선:

- 작은 root 또는 단일 파일에서는 `python`을 먼저 쓰는 `backend="smart"` 모드

향후 개선 후보:

- 검색 root 크기나 파일 수를 더 정교하게 샘플링한 adaptive backend 선택

### 2. ignore 정책은 검색 품질에 큰 영향을 준다

`ripgrep`, `ack`, `ag`는 코드 검색에서 ignore 파일과 숨김/바이너리 파일 처리가 중요하다는 점을 공통으로 보여준다.

현재 Python backend는 다음 디렉터리를 수동 제외한다.

```text
.git, .hg, .svn, __pycache__, .venv, venv, node_modules,
.mypy_cache, .pytest_cache, .ruff_cache
```

향후 개선 후보:

- symlink 순회 정책 명시
- `exclude` 옵션 추가

구현된 개선:

- `pathspec`이 설치돼 있으면 Python backend도 `.gitignore`/`.ignore` 파일을 파싱한다.

### 3. 결과 형식은 사람이 보는 출력보다 tool JSON에 더 엄격해야 한다

LLM tool 결과는 `path`, `line_number`, `column`, `line`, `match`, `backend`, `truncated` 의미가 흔들리면 후속 추론이 어려워진다.

현재 개선한 점:

- `max_results`와 결과 수가 같다는 이유만으로 `truncated=true`로 표시하지 않는다.
- 내부적으로 `max_results + 1`개를 조회해 실제 추가 결과가 있을 때만 `truncated=true`로 표시한다.
- PowerShell 파이프 입력처럼 JSON 앞에 UTF-8 BOM이 붙는 경우도 허용한다.

### 4. 구조 단위 검색은 별도 계층으로 보는 편이 낫다

함수/클래스/호출 관계 검색은 grep 계열보다 `ast-grep` 같은 AST 기반 도구가 자연스럽다. `pygreptool`이 이 영역을 지원하려면 기존 텍스트 검색 API에 억지로 끼우기보다 별도 backend 또는 별도 tool로 분리하는 편이 좋다.

## 참고 링크

- `ripgrep`: https://github.com/BurntSushi/ripgrep
- GNU `grep` manual page: https://man7.org/linux/man-pages/man1/grep.1.html
- `ack`: https://github.com/beyondgrep/ack3
- `ack` documentation on MetaCPAN: https://metacpan.org/dist/ack/view/ack
- The Silver Searcher: https://github.com/ggreer/the_silver_searcher
- The Silver Searcher man page: https://github.com/ggreer/the_silver_searcher/blob/master/doc/ag.1.md
- `ugrep`: https://github.com/Genivia/ugrep
- `ast-grep`: https://github.com/ast-grep/ast-grep
- `ast-grep` docs: https://ast-grep.github.io/
- `comby`: https://github.com/comby-tools/comby
- `comby` docs: https://comby.dev/
- Python `pathlib`: https://docs.python.org/3/library/pathlib.html
- Python `fnmatch`: https://docs.python.org/3/library/fnmatch.html
- Python `json`: https://docs.python.org/3/library/json.html
