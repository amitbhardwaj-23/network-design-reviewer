content = open("debug_extraction.py").read()
old = "    spec, error = validate_spec(state[\"raw_llm_output\"])"
new = "    spec, error, warnings = validate_spec(state[\"raw_llm_output\"])"
assert old in content, "anchor not found"
content = content.replace(old, new, 1)

old2 = '''    else:
        print(f"\\n--- VALIDATION PASSED ---")
        print(f"Devices ({len(spec.devices)}): {[d.id for d in spec.devices]}")'''
new2 = '''    else:
        print(f"\\n--- VALIDATION PASSED ---")
        if warnings:
            print("--- AUTO-REPAIR WARNINGS ---")
            for w in warnings:
                print(f"  ! {w}")
        print(f"Devices ({len(spec.devices)}): {[d.id for d in spec.devices]}")'''
assert old2 in content, "anchor2 not found"
content = content.replace(old2, new2, 1)

open("debug_extraction.py", "w").write(content)
print("debug_extraction.py patched")
