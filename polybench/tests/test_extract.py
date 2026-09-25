from hypothesis import given, strategies as st
from polybench.extract import extract_code
from polybench.schemas import Language

@given(st.text(), st.text())
def test_extract_with_fences(prose_before, prose_after):
    code = "def test():\n    pass"
    raw = f"{prose_before}\n```python\n{code}\n```\n{prose_after}"
    assert extract_code(raw, Language.python) == code

def test_extract_python_fence():
    raw = "Here is the code:\n```python\ndef test():\n    pass\n```\nDone."
    assert extract_code(raw, Language.python) == "def test():\n    pass"

def test_extract_no_fence_heuristic():
    raw = "def test():\n    return 42"
    assert extract_code(raw, Language.python) == raw

def test_extract_empty():
    assert extract_code("", Language.python) is None
    assert extract_code(None, Language.python) is None

def test_extract_generic_fence():
    raw = "```\nsome generic code\n```"
    assert extract_code(raw, Language.python) == "some generic code"
    raw_other = "```js\nconst x = 1;\n```"
    assert extract_code(raw_other, Language.python) == "const x = 1;"

def test_extract_js_go_heuristics():
    raw_js = "const my_func = () => {}"
    assert extract_code(raw_js, Language.javascript) == raw_js
    raw_go = "func main() {}"
    assert extract_code(raw_go, Language.go) == raw_go
    raw_none = "plain text with no keywords"
    assert extract_code(raw_none, Language.python) is None

