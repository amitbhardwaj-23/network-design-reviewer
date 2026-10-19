content = open("app.py").read()

old_import = "from diagram_renderer.graph import render_lld_to_diagram"
new_import = "from diagram_renderer.graph import render_lld_to_diagram\nfrom visual_reviewer.visual_graph import review_diagram_image"
assert old_import in content, "import anchor not found - paste app.py content if this fails"
content = content.replace(old_import, new_import, 1)

visual_reviewer_section = '''

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
'''

content = content.rstrip("\n") + "\n" + visual_reviewer_section
open("app.py", "w").write(content)
print("app.py patched with Visual Reviewer section")
