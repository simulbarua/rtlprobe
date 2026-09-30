**Meeting Type:** Advisor
**Date:** 2026-09-10
**Start–End Time:** 12:40pm - 1:15pm
**Location/Mode:** In-person

**Attendees:**
- Prof. Charan Bhaskar (Advisor)
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- Revised the project proposal in response to earlier feedback that the description read as too general.
- Reworked the framing around societal impact — digital hardware in healthcare, automotive, avionics, industrial systems, and AI infrastructure, and the fact that defects in fabricated silicon cannot be patched.

### 2) Accomplished During This Meeting

- Project finalized: **RTLProbe — AI-Assisted Root-Cause Analysis for Reliable Digital Hardware**.
- Impact framing agreed: pre-silicon verification is the last point at which a hardware defect can be removed, debugging is its largest bottleneck, and time spent on manual debug is time not spent finding further defects.
- Initial approach agreed: mutation-based fault injection into open-source RTL to generate labelled training data, with a multimodal model drawing on RTL source, simulation results, design structure, and netlist-level information.
- Agreed the focus for the next advisor meeting: dataset structure and initial methodology.

### 3) Issues / Blockers

- Evaluation methodology not yet defined.
- Localization granularity (module / block / line) not yet decided.

### 4) Action Items

- Action: Begin assembling the open-source RTL dataset and define mutation criteria.

### 5) Plans / Goals for Next Week

- Present the dataset structure (columns, repository list) and initial methodology.
- Define work distribution and individual responsibilities across the team.
- Learning curve for machine learning and domain.