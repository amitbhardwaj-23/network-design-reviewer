content = open("graph.py").read()

old1 = '''    output_path: Optional[str]
    failed: bool'''
new1 = '''    output_path: Optional[str]
    failed: bool
    warnings: list[str]'''
assert old1 in content, "anchor1 not found"
content = content.replace(old1, new1, 1)

old2 = '''    spec, error = validate_spec(state["raw_llm_output"])
    if error:
        retry_count = state.get("retry_count", 0) + 1
        return {**state, "spec": None, "last_error": error, "retry_count": retry_count}
    return {**state, "spec": spec, "last_error": None}'''
new2 = '''    spec, error, warnings = validate_spec(state["raw_llm_output"])
    if error:
        retry_count = state.get("retry_count", 0) + 1
        return {**state, "spec": None, "last_error": error, "retry_count": retry_count}
    return {**state, "spec": spec, "last_error": None, "warnings": warnings}'''
assert old2 in content, "anchor2 not found"
content = content.replace(old2, new2, 1)

open("graph.py", "w").write(content)
print("graph.py patched")
