# Knowledge Base — Network Design Reviewer

Seed this directory with .md or .txt files containing architectural standards.

## Recommended sources

### Public / freely available
- NIST SP 800-207 (Zero Trust Architecture) — convert PDF to .txt
  Download: https://csrc.nist.gov/publications/detail/sp/800-207/final
- CIS Controls v8 — download CSV/PDF and convert to .md
  Download: https://www.cisecurity.org/controls/v8
- NIST Cybersecurity Framework 2.0 — convert PDF sections to .md

### Your own IP (highest value — makes this tool uniquely yours)
- Your HLD/LLD templates from previous engagements
- Architecture governance documents and principles
- Kill Switch Process and change governance documents
- Reference architecture summaries you have written
- TOGAF ADM phase notes from your Practitioner work
- Zscaler Zero Trust Exchange principles (your own notes)

### Cisco CVD excerpts (key principles only — not full PDFs)
- SDA Campus Design Guide key principles
- ACI multi-tier design principles
- SD-WAN WAN Edge design guidance

## After adding files, seed the KB
python retriever.py seed
