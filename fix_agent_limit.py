content = open("agent.py").read()

old = '''    final = app.invoke(initial)
    return final["report"]'''

new = '''    final = app.invoke(initial, config={"recursion_limit": 15})
    return final["report"]'''

assert old in content, "anchor not found — paste agent.py content if this fails"
content = content.replace(old, new, 1)
open("agent.py", "w").write(content)
print("agent.py patched with recursion_limit=15")
