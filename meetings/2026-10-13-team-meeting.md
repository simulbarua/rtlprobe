**Meeting Type:** Team-Only
**Date:** 10-13-2026
**Start–End Time:** 11:00 am
**Location/Mode:** Zoom

**Attendees:**
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- Analysed the DeepRTL dataset: 434,697 line-level code and description pairs, around 2,200 block-level and 59,450 module-level, mostly GPT-4 annotated.
- Established DeepRTL cannot be reproduced from it, since the published training used eight A800 80GB GPUs and the paper gives no hyperparameters.
- Continued dataset construction and pipeline work.

### 2) Accomplished During This Meeting

- Reviewed the dataset analysis and the conclusion that reproduction is not feasible.
- Discussed training a Verilog-adapted encoder from the public CodeT5+ checkpoint using the released line-level pairs as an alternative.
- Confirmed GPU workstation availability for model work.

### 3) Issues / Blockers

- Labelled bug cases still required before any model can be compared on the actual task.

### 4) Action Items

- Action: Implement the encoder training approach and set up the GPU workstation | Owner: Dipti
- Action: Continue dataset construction | Owner: Simul
- Action: Continue pipeline automation | Owner: Sriram

### 5) Plans / Goals for Next Meeting

- Training script and GPU environment ready.
