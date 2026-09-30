**Meeting Type:** Team-Only
**Date:** 2026-09-15
**Start–End Time:** 4pm-5pm
**Location/Mode:** Zoom

**Attendees:**
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- Collected and organized open-source RTL repositories and libraries.
- Compiled a spreadsheet of candidate RTL datasets for prototype training and evaluation.
- Identified PicoRV32 as the initial design for pipeline bring-up.

### 2) Accomplished During This Meeting

- Reviewed the collected RTL dataset spreadsheet.
- Confirmed the dataset approach: mutation-based fault injection into open-source RTL, giving ground-truth bug locations for supervised training.
- Divided work three ways — dataset preparation and mutation (Simul), simulation infrastructure (Sriram), model exploration (Dipti).
- Selected the simulation toolchain: Icarus Verilog with Python automation, producing logs and VCD waveform output.

### 3) Issues / Blockers

- Approach for reducing the number of test cases needed per design still undefined.

### 4) Action Items

- Action: Upload dataset spreadsheet and related documents to the shared drive | Owner: Simul
- Action: Send PicoRV32 test script to Sriram and set up the simulation environment together | Owner: Simul | Due: 2026-09-29
- Action: Share relevant literature and papers with the team | Owner: Simul 
- Action: Prepare dataset structure (columns, repo list) | Owner: Simul | Due: 2026-09-17
- Action: Install simulation toolchain (Icarus Verilog and supporting tools) | Owner: Sriram | Due: 2026-09-29
- Action: Run PicoRV32 simulation end to end and automate the pipeline in Python | Owner: Sriram | Due: 2026-09-29
- Action: Fill in workbook sections (tools, pipeline, environments) and share for review | Owner: Sriram | Due: 2026-09-29
- Action: Update meeting logs, including prior meetings with Prof. Charan Bhaskar | Owner: Dipti | Due: 2026-09-29
- Action: Explore and document candidate models (CodeBERT, graph-based) for RTL, logs, waveforms, synthesis | Owner: Dipti | Due: 2026-09-29
- Action: Document relevant literature, particularly CodeBERT applied to RTL | Owner: Dipti | Due: 2026-09-29

### 5) Plans / Goals for Next Two Weeks

- Present dataset structure and initial methodology to the advisor.
- Working simulation pipeline running PicoRV32 end to end with log and VCD output.
- Initial mutation criteria defined for fault injection.
- Documented comparison of candidate model architectures.
