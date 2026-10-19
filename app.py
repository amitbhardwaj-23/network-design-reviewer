"""app.py — Streamlit UI for the Network Design Reviewer."""
import os, tempfile, time
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent import review_design
from retriever import kb_status, seed_standards
from diagram_renderer.graph import render_lld_to_diagram
from visual_reviewer.visual_graph import review_diagram_image
from config_generator.config_graph import generate_configs_for_lld
import zipfile
import io

st.set_page_config(page_title="Network Design Reviewer", page_icon="[REVIEW]", layout="wide")
st.title("Network Design Reviewer")
st.caption("Agentic AI review of HLD/LLD documents against architectural standards")

with st.sidebar:
    st.header("Configuration")
    status = kb_status()
    if status["chunks"] == 0:
        st.warning("Knowledge base is empty")
        st.caption("Add .md/.txt files to ./knowledge_base/ then click Seed below")
        if st.button("Seed Knowledge Base"):
            with st.spinner("Seeding..."):
                seed_standards()
            st.success("Done! Refresh to see updated chunk count.")
            st.rerun()
    else:
        st.success(f"KB ready: {status['chunks']} chunks indexed")
    st.divider()
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    st.caption(f"Model: {model} (local Ollama)")
    st.caption("Swap to Bedrock: update .env")
    st.divider()
    st.caption("Built by Enterprise Architect | LangGraph + ChromaDB + Ollama")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("Upload Design Document")
    uploaded = st.file_uploader("Upload HLD or LLD", type=["md","txt","docx"])
    st.caption("— or paste design text directly —")
    pasted = st.text_area("Paste design text", height=280,
                          placeholder="# Network HLD\n\n## Scope\n...",
                          label_visibility="collapsed")
    run = st.button("Run Review", type="primary",
                    disabled=(not uploaded and not pasted.strip()),
                    use_container_width=True)
    with st.expander("Load sample design for demo"):
        st.caption("Paste this into the text area above to test the reviewer:")
        st.code(Path("sample_designs/campus_hld_sample.md").read_text()
                if Path("sample_designs/campus_hld_sample.md").exists()
                else "Run setup script to generate sample.", language="markdown")

with col2:
    st.subheader("Review Report")
    placeholder = st.empty()

if run:
    if uploaded:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue()); tmp_path = tmp.name
        design_text = uploaded.getvalue().decode("utf-8", errors="ignore") if suffix in (".md", ".txt") else None
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="w") as tmp:
            tmp.write(pasted); tmp_path = tmp.name
        design_text = pasted

    with col2:
        bar = st.progress(0)
        status_box = st.status("Running agentic review...", expanded=True)
        with status_box:
            st.write("Parsing design document...")
            bar.progress(20); time.sleep(0.3)
            st.write("Retrieving architectural standards...")
            bar.progress(40)
            st.write("Agent reviewing sections...")
            bar.progress(60)
            try:
                report = review_design(tmp_path)
                bar.progress(90)
                st.write("Generating structured report...")
                time.sleep(0.2); bar.progress(100)
                status_box.update(label="Review complete!", state="complete")
            except Exception as e:
                status_box.update(label=f"Error: {e}", state="error")
                st.error(str(e)); report = None
            finally:
                os.unlink(tmp_path)

    if report:
        st.session_state["report"] = report
        st.session_state["design_text"] = design_text

if st.session_state.get("report"):
    with col2:
        placeholder.markdown(st.session_state["report"])
        st.download_button("Download Report (.md)", data=st.session_state["report"],
                           file_name="design_review_report.md",
                           mime="text/markdown", use_container_width=True)
        st.divider()
        if st.session_state.get("design_text"):
            if st.button("Render Diagram", use_container_width=True):
                with st.spinner("Extracting topology and rendering diagram..."):
                    diagram_result = render_lld_to_diagram(
                        lld_text=st.session_state["design_text"], kb_context="")
                st.session_state["diagram_result"] = diagram_result
            dr = st.session_state.get("diagram_result")
            if dr:
                if dr.get("failed"):
                    st.error(f"Diagram rendering failed: {dr.get('last_error')}")
                else:
                    st.success("Diagram rendered.")
                    with open(dr["output_path"], "rb") as f:
                        st.download_button("Download Diagram (.drawio)", data=f,
                                           file_name="network_lld.drawio",
                                           mime="application/xml", use_container_width=True)

            st.divider()
            if st.button("Generate Device Configs", use_container_width=True):
                with st.spinner("Extracting topology and config parameters, generating device configs... this can take several minutes."):
                    config_result = generate_configs_for_lld(
                        lld_text=st.session_state["design_text"], kb_context="")
                st.session_state["config_result"] = config_result

            cr = st.session_state.get("config_result")
            if cr:
                if cr.get("failed"):
                    st.error(f"Config generation failed: {cr.get('last_error')}")
                else:
                    warnings = cr.get("warnings") or []
                    if warnings:
                        with st.expander(f"{len(warnings)} item(s) flagged during generation — review before deploying", expanded=False):
                            for w in warnings:
                                st.warning(w)
                    config_paths = cr.get("config_paths") or []
                    st.success(f"Generated {len(config_paths)} device config file(s).")

                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for path in config_paths:
                            zf.write(path, arcname=path.split("/")[-1])
                    zip_buffer.seek(0)

                    st.download_button(
                        "Download All Configs (.zip)",
                        data=zip_buffer,
                        file_name="device_configs.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )

                    with st.expander("Preview individual configs"):
                        for path in config_paths:
                            device_name = path.split("/")[-1].replace(".cfg", "")
                            with open(path, "r") as f:
                                st.text_area(device_name, f.read(), height=150, key=f"cfg_preview_{device_name}")
        else:
            st.caption("Diagram rendering and config generation currently support pasted text or .md/.txt uploads (.docx not yet supported).")


# ============================================================
# Module 4: Visual Diagram Reviewer - independent of the text review flow
# ============================================================
st.divider()
st.subheader("Visual Diagram Reviewer")
st.caption("Upload an existing network diagram image to extract and validate its topology.")

uploaded_image = st.file_uploader(
    "Upload a diagram image",
    type=["png", "jpg", "jpeg"],
    key="visual_reviewer_upload",
)

if uploaded_image is not None:
    st.image(uploaded_image, caption="Uploaded diagram", use_container_width=True)

    if st.button("Review Diagram Image", use_container_width=True):
        import tempfile as _tempfile
        import os as _os
        suffix = "." + uploaded_image.name.split(".")[-1].lower()
        tmp_img = _tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_img.write(uploaded_image.getvalue())
        tmp_img.close()
        tmp_img_path = tmp_img.name

        with st.spinner("Sending image to Claude for topology extraction... this calls a paid API."):
            visual_result = review_diagram_image(tmp_img_path)
        st.session_state["visual_result"] = visual_result
        _os.unlink(tmp_img_path)

    vr = st.session_state.get("visual_result")
    if vr:
        if vr.get("failed"):
            st.error("Visual review failed: " + str(vr.get("last_error")))
        else:
            warnings = vr.get("warnings") or []
            if warnings:
                with st.expander(str(len(warnings)) + " item(s) flagged during extraction - review before trusting the result", expanded=False):
                    for w in warnings:
                        st.warning(w)

            spec = vr["spec"]
            st.success("Extracted " + str(len(spec.devices)) + " device(s) and " + str(len(spec.links)) + " link(s).")

            with st.expander("Extracted topology", expanded=True):
                for d in spec.devices:
                    st.text(d.id + "  (" + d.type + ", " + d.tier + " tier) - '" + d.label + "'")
                st.text("")
                for l in spec.links:
                    st.text(l.source + " -> " + l.target + "  (" + l.label + ")")

            st.download_button(
                "Download reconstructed diagram (.drawio)",
                data=vr["xml"],
                file_name="reconstructed_from_image.drawio",
                mime="application/xml",
                use_container_width=True,
            )
            st.caption("Compare this against the uploaded image above to check the extraction is accurate before trusting it.")
