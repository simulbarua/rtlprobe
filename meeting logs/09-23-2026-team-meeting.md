**Meeting Type:** Team-Only
**Date:** 09-23-2026
**Start–End Time:** 1:00-1:45pm
**Location/Mode:** Zoom

**Attendees:**
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- Ran PicoRV32 design and testbench simulations end to end; results now stored with timestamps in a results folder, with waveform files dumped for debugging.
- Completed the automation setup for compilation output and folder structure, except for AST graph extraction.
- Ran the first encoder screening test on Verilog statements, comparing CodeBERT and UniXcoder.
- Investigated DeepRTL and RTLCoder as Verilog-trained alternatives.

### 2) Accomplished During This Meeting

- Reviewed the simulation pipeline: rather than inspecting full waveforms manually, the approach is to extract specific signal values at the point of test failure to confirm faulty values. 
- Agreed the mutation engine will be built in Python using AST-based analysis, avoiding manual dataset preparation.
- Agreed to finalise the directory structure before proceeding with automation, and to drive the pipeline from a JSON configuration file so it stays generic across designs with minimal modification.
- Dipti presented encoder evaluation findings: CodeBERT and UniXcoder both produced low silhouette scores, meaning they do not cluster statement vectors well, despite reasonable kNN accuracy at the individual level. DeepRTL's published release includes the fine-tuning dataset but not the model weights. RTLCoder is usable but large, and would need additional compute.
- Agreed to continue evaluating multiple encoders and to assess them properly once labelled data is available from the mutation engine.
- Noted that fusion of multiple model outputs has not yet been explored and needs a defined approach.
- Reviewed the project workbook against the rubric; project architecture, implementation plan, and project schedule are missing and must be added before the 1 October deadline.

### 3) Issues / Blockers

- DeepRTL model weights not publicly released — only the fine-tuning dataset is available.
- RTLCoder requires GPU resources not currently available; HPC or cloud access needs to be arranged.
- Fusion approach for combining per-modality outputs not yet defined.
- AST graph extraction still outstanding; multiple candidate solutions to evaluate.
- Workbook incomplete against the rubric ahead of the 1 October submission.

### 4) Action Items

- Action: Finalise the GitHub repository structure and share the document for review | Owner: Simul | Due: 09-27-26
- Action: Share the bug-finding dataset with Dipti for model evaluation | Owner: Simul 
- Action: Email the DeepRTL authors to request access to the model weights | Owner: Dipti 
- Action: Assess feasibility of running RTLCoder on available compute  | Owner: Dipti 
- Action: Compile and share the dependency list and JSON configuration file for the simulation pipeline | Owner: Sriram | 
- Action: Review the workbook against the rubric and add the missing sections (project architecture, implementation plan, project schedule) | Owner: Sriram | Due: Friday

### 5) Plans / Goals for Next Meeting

- Finalised repository and directory structure in place.
- Mutation engine producing labelled mutants with ground-truth fault locations.
- Decision on compute resources for running larger models.
- Workbook complete and circulated for review ahead of the 1 October deadline.
