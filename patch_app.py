content = open("app.py").read()

# 1. Add the import
old_import = 'from retriever import kb_status, seed_standards'
new_import = 'from retriever import kb_status, seed_standards\nfrom diagram_renderer.graph import render_lld_to_diagram'
assert old_import in content, "import anchor not found"
content = content.replace(old_import, new_import, 1)

# 2. Capture the original design text before the temp file is used
old_block = '''if run:
    if uploaded:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue()); tmp_path = tmp.name
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="w") as tmp:
            tmp.write(pasted); tmp_path = tmp.name'''
new_block = '''if run:
    if uploaded:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue()); tmp_path = tmp.name
        design_text = uploaded.getvalue().decode("utf-8", errors="ignore") if suffix in (".md", ".txt") else None
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="w") as tmp:
            tmp.write(pasted); tmp_path = tmp.name
        design_text = pasted'''
assert old_block in content, "run block anchor not found"
content = content.replace(old_block, new_block, 1)

# 3. Add the Render Diagram button after the report download button
old_tail = '''    if report:
        placeholder.markdown(report)
        st.download_button("Download Report (.md)", data=report,
                           file_name="design_review_report.md",
                           mime="text/markdown", use_container_width=True)'''
new_tail = '''    if report:
        placeholder.markdown(report)
        st.download_button("Download Report (.md)", data=report,
                           file_name="design_review_report.md",
                           mime="text/markdown", use_container_width=True)
        st.divider()
        if design_text:
            if st.button("Render Diagram", use_container_width=True):
                with st.spinner("Extracting topology and rendering diagram..."):
                    diagram_result = render_lld_to_diagram(lld_text=design_text, kb_context="")
                if diagram_result.get("failed"):
                    st.error(f"Diagram rendering failed: {diagram_result.get('last_error')}")
                else:
                    st.success("Diagram rendered.")
                    with open(diagram_result["output_path"], "rb") as f:
                        st.download_button("Download Diagram (.drawio)", data=f,
                                           file_name="network_lld.drawio",
                                           mime="application/xml", use_container_width=True)
        else:
            st.caption("Diagram rendering currently supports pasted text or .md/.txt uploads (.docx not yet supported).")'''
assert old_tail in content, "report block anchor not found"
content = content.replace(old_tail, new_tail, 1)

open("app.py", "w").write(content)
print("app.py patched successfully — 3 changes applied")
