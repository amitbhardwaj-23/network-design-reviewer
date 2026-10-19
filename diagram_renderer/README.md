# Diagram Renderer — drop-in for network-design-reviewer

Built to match your actual environment: reads `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
straight from your existing `.env`, uses `langchain-ollama` + `langgraph`
(both already in your venv), and writes output next to your other files.

## 1. Copy files onto the VM

From your local machine (or wherever you're reading this), copy the 6 files
in this folder into a new subfolder of your project:

```bash
# on vm01-ai-lab
mkdir -p ~/network-design-reviewer/diagram_renderer
# copy schema.py, validate.py, render.py, prompts.py, graph.py, test_pipeline.py
# into that folder (scp, or paste via nano/vim — whatever you used for the repo)
```

## 2. Test the deterministic half first (no Ollama needed)

```bash
cd ~/network-design-reviewer/diagram_renderer
source ../venv/bin/activate
python3 test_pipeline.py
```

You should see `OK` three times and a `test_output.drawio` file. Open it at
[app.diagrams.net](https://app.diagrams.net) (File → Open) to confirm it
actually renders — 5 devices, core/distribution/access tiers, firewall at
the edge.

## 3. Test the real Ollama path

```bash
python3 -c "
from graph import render_lld_to_diagram
result = render_lld_to_diagram(
    lld_text='Core switch CORE1 connects to distribution switch DIST1 via a 10G uplink. A perimeter firewall FW1 sits in front of CORE1 on a 1G WAN link.',
    kb_context=''
)
print('failed:', result.get('failed'))
print('output_path:', result.get('output_path'))
print('last_error:', result.get('last_error'))
"
```

This calls your real `llama3.2` model through `ChatOllama`. First run will be
slower (model already loaded in memory from your reviewer testing, so should
be quick) — if it fails, the `last_error` field tells you exactly what went
wrong (bad JSON, schema mismatch, or a dangling link reference).

## 4. Wire into app.py

Add near your other imports:

```python
from diagram_renderer.graph import render_lld_to_diagram
```

Add a button after your existing review output (adjust variable names to
match whatever holds the approved LLD text and retrieved KB context in your
actual `app.py`):

```python
if st.button("Render Diagram"):
    with st.spinner("Extracting topology and rendering diagram..."):
        result = render_lld_to_diagram(
            lld_text=reviewed_lld_text,      # whatever variable holds the approved text
            kb_context=retrieved_context,     # whatever variable holds retriever.py's output
        )
    if result.get("failed"):
        st.error(f"Rendering failed after retries: {result.get('last_error')}")
    else:
        st.success("Diagram rendered.")
        with open(result["output_path"], "rb") as f:
            st.download_button(
                "Download .drawio file",
                f,
                file_name="network_lld.drawio",
                mime="application/xml",
            )
```

## 5. Optional: set a custom output directory

By default renders go to `./outputs/network_lld.drawio` relative to wherever
you run Streamlit from. To change that, add one line to your `.env`:

```
DIAGRAM_OUTPUT_DIR=./rendered_diagrams
```

## What's tested vs. what to watch for

Tested here (via `test_pipeline.py`): JSON validation, XML generation, XML
structural validation — all deterministic, no Ollama dependency, will behave
identically on your VM.

Not yet tested against your real LLD documents: run a few of your
`sample_designs/` files through `render_lld_to_diagram()` directly (bypass
Streamlit) first, and eyeball the extracted JSON in `raw_llm_output` before
worrying about the rendered diagram — if the device list is right, the
diagram is guaranteed right, since rendering itself is deterministic.
