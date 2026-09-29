# NOTICE — WS-1 Golden Dataset attribution

The document **content** in this golden dataset is derived from:

- **Nemotron-PII** — NVIDIA — https://huggingface.co/datasets/nvidia/Nemotron-PII
  Licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**
  (https://creativecommons.org/licenses/by/4.0/).

Nemotron-PII is a **fully synthetic** dataset (no real personal data). We sampled a
balanced slice, mapped its PII labels to our approved taxonomy (financial /
government_id / health), and **rendered** each record into a document format
(TXT / PDF / PNG / DOCX / XLSX). These rendered documents are adaptations of the
CC BY 4.0 source and are redistributed here under the same terms, with attribution.

The **clean, PII-free documents** (`source_dataset = "generated-clean"`) are original,
synthetic, benign text authored for this repository.

No real personal data is present in this dataset.
