**Meeting Type:** Team-Only
**Date:** 10-26-2026
**Start–End Time:** 11:00 am
**Location/Mode:** Zoom

**Attendees:**
- Simul Barua
- Sriram Sridhar
- Dipti Ghiya

---

### 1) Accomplished Since Last Meeting

- Simul completed pilot work on the dataset generation agent.
- Dipti ran the expanded model comparison across several projects and on designs not seen in training, and continued testing and fine-tuning CodeBERT and StarCoder2 on the sample data available.
- Sriram continued pipeline work; UVM support added for OpenTitan IPs.

### 2) Accomplished During This Meeting

- Discussed the difficulty of identifying bugs without a reliable reference, and whether the specification could serve that role alongside RTL. A C++ model was mentioned as another possible reference.
- **Dataset approach:** the agent inserts bug mutations and maps them to specification lines. Target is a dataset in the thousands, with 5 to 10 examples per bug type reviewed to assess agent output.
- **Evaluation approach:** compare modality contributions by supplying a frontier model with different inputs (failure logs, RTL, specification, waveforms, AST graphs) and comparing against the team's own trained model, exposed as an MCP server.
- Deliverables confirmed as a benchmark dataset and an agent/model.
- Reviewed submission requirements: individual design specs and log books due Tuesday, reviewed together before going to the advisor. Workbook sections needing update are evaluation methodology, implementation plan and progress, and project schedule.
- Confirmed the advisor meeting Thursday to show the dataset, and the presentation Friday.

### 3) Action Items

- Action: Continue testing and fine-tuning StarCoder2, compare against CodeBERT | Owner: Dipti
- Action: Update the meeting notes in GitHub | Owner: Dipti
- Action: Prepare a brief update for the advisor on dataset rows identified and model progress | Owner: Dipti
- Action: Deploy the agent to the cloud server after the midterm exam | Owner: Simul
- Action: Give Sriram and Dipti access to the cloud server and agent dashboard | Owner: Simul
- Action: Send Dipti dataset samples by 30 or 31 October for model training | Owner: Simul
- Action: Update the workbook sections and send it with the individual logs to the advisor by Tuesday | Owner: Simul
- Action: Send Sriram files to check into the GitHub repository | Owner: Simul
- Action: Complete and submit the individual log report | Owner: Sriram
- Action: Send the meeting notes to the team once received from Zoom | Owner: Sriram

### 4) Plans / Goals for Next Meeting

- Agent deployed and dashboard available for review.
- Dataset samples available for model training.
- Model selection and remaining inputs discussed.
- Team meets Tuesday evening to review individual log reports before submission; advisor meeting Thursday, presentation Friday.
