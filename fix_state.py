content = open("app.py").read()

old = '''    if report:
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

new = '''    if report:
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
        else:
            st.caption("Diagram rendering currently supports pasted text or .md/.txt uploads (.docx not yet supported).")'''

assert old in content, "anchor not found — paste app.py content if this fails"
content = content.replace(old, new, 1)
open("app.py", "w").write(content)
print("app.py patched for session_state persistence")
