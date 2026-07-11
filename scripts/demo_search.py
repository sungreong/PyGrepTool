from __future__ import annotations

from pygreptool import search


if __name__ == "__main__":
    results = search("TODO", "examples", backend="auto", regex=False)
    for result in results:
        print(f"{result.backend}: {result.path}:{result.line_number}:{result.column}: {result.line}")
