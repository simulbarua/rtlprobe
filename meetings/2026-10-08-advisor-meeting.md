**Meeting Type:** Advisor
**Date:** 10-08-2026
**Start–End Time:** 9:30 am
**Location/Mode:** In-person

**Attendees:**
- Dr. Vidhyacharan Bhaskar (Advisor)
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- Completed the initial encoder screening on PicoRV32 statements. CodeBERT and UniXcoder showed no meaningful advantage over a TF-IDF word-count baseline, and clustering quality was poor across all methods. Noted that the test used keyword-derived labels, so it cannot separate surface matching from semantic understanding.
- Investigated Verilog-trained models. Established that DeepRTL weights are not publicly released, only the fine-tuning dataset, and that RTLCoder is the viable downloadable alternative.
- Confirmed GPU availability for model work.
- Continued dataset construction and simulation pipeline work.
- Produced the system architecture diagram and reviewed the workbook.

### 2) Accomplished During This Meeting

- Presented progress on model evaluation and the current state of the dataset and pipeline work.
- Advisor gave pointers on model training.

### 3) Issues / Blockers

- DeepRTL weights unavailable.
- Limited labelled data available for model evaluation.

### 4) Action Items

- Action: Continue model selection work based on the advisor's feedback | Owner: Dipti
- Action: Continue dataset construction | Owner: Simul
- Action: Continue pipeline automation | Owner: Sriram

### 5) Plans / Goals for Next Meeting

- Progress on model selection.
- Progress on dataset construction and the simulation pipeline.
