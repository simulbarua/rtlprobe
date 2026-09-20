**Meeting Type:** Team-Only
**Date:** [FILL]
**Start–End Time:** [TBD]
**Location/Mode:** [In-person / Zoom]

**Attendees:**
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- [FILL — individual reading or preliminary work done before this meeting]

### 2) Accomplished During This Meeting

- Agreed the project direction: a multimodal machine learning approach to RTL debugging and bug localization.
- Defined the problem: when a test fails, engineers manually correlate simulation logs, waveforms, and linting reports to trace the failure back to the responsible RTL, which is slow and expert-intensive.
- Agreed the system's intended function: take a failing simulation and return a ranked list of the RTL locations most likely responsible.
- Identified the information sources the model would draw on: RTL source code, design structure, verification results, and netlist-level information.
- Divided work across the team:
  - **Simul** — dataset collection and preparation, mutation criteria for fault injection, overall pipeline
  - **Sriram** — simulation toolchain and automation, running designs and collecting logs and waveform output
  - **Dipti** — model exploration across modalities, literature review, meeting documentation
- Drafted the project abstract for presentation.

### 3) Issues / Blockers

- Scope of the four information sources not yet bounded — which are built first and which are deferred.
- No labelled dataset of RTL bugs available; fault injection needed to generate ground truth.
- Evaluation approach not yet defined.
- Tool access and licensing constraints still to be confirmed.

### 4) Action Items

- Action: Draft and finalise the project abstract for presentation | Owner: Simul | Due: [TBD]
- Action: [FILL] | Owner: Sriram | Due: [TBD]
- Action: [FILL] | Owner: Dipti | Due: [TBD]

### 5) Plans / Goals for Next Meeting

- Present the abstract and gather feedback.
- Begin identifying open-source RTL repositories suitable for dataset construction.
- Begin surveying candidate model architectures for each information source.
