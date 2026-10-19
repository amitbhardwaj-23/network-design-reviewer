content = open("app.py").read()

# 1. Add the import, right after the diagram renderer import
old_import = "from diagram_renderer.graph import render_lld_to_diagram"
new_import = (
    "from diagram_renderer.graph import render_lld_to_diagram\n"
    "from config_generator.config_graph import generate_configs_for_lld\n"
    "import zipfile\n"
    "import io"
)
assert old_import in content, "import anchor not found"
content = content.replace(old_import, new_import, 1)

# 2. Add the Generate Configs button right after the Render Diagram block,
#    still inside the same `if st.session_state.get("design_text"):` branch,
#    using the same session_state persistence pattern so it survives reruns.
old_block = '''            dr = st.session_state.get("diagram_result")
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

new_block = '''            dr = st.session_state.get("diagram_result")
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
            st.caption("Diagram rendering and config generation currently support pasted text or .md/.txt uploads (.docx not yet supported).")'''

assert old_block in content, "render-diagram block anchor not found"
content = content.replace(old_block, new_block, 1)

open("app.py", "w").write(content)
print("app.py patched with Generate Configs button")
