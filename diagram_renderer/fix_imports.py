content = open("graph.py").read()

old = '''import os
from typing import TypedDict, Optional
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END

from schema import NetworkDiagramSpec
from validate import validate_spec, validate_xml
from render import render_xml
from prompts import build_extraction_prompt'''

new = '''import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import TypedDict, Optional
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END

from schema import NetworkDiagramSpec
from validate import validate_spec, validate_xml
from render import render_xml
from prompts import build_extraction_prompt'''

assert old in content, "anchor not found — paste graph.py content if this fails"
content = content.replace(old, new, 1)
open("graph.py", "w").write(content)
print("graph.py patched")
