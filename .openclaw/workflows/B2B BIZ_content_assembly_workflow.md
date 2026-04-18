# Antigravity Workflow: AI Content Assembly Line (Turnkey Delivery)
**Target:** 6-Agent Media Production Matrix (B2B AI Drama Factory)

## 1. Workflow Objective & Core Discipline
This workflow defines the high-speed, automated production line for B2B short dramas. It prioritizes Speed over Perfection and strictly enforces client revision limits based on their subscription tiers.

* **Strict Discipline 1:** The 3-Second Hook Rule. No script or video can proceed if the first 3 seconds fail to address a critical pain point.
* **Strict Discipline 2:** Subscription Boundary Enforcement. `$$PM` MUST veto any client revision request that exceeds the allowed quota.
* **Strict Discipline 3:** Zero-Hallucination Delivery. No video is delivered to the human Account Manager without `$$QA`'s visual and legal clearance.

## 2. Global Execution Rules
* **Orchestrator:** `$$PM` controls the central pipeline, client interactions, and phase transitions.
* **Independent Hunter:** `$$SDR` operates asynchronously at the top of the funnel to constantly feed leads to `$$PM`.
* **Collaboration Syntax:** Agents MUST actively pass the baton to the next role using the exact format: `>> [To $$ROLE]: <Instruction>`.

---

## 3. The Assembly Line Protocols

### [Protocol O: Outbound & Lead Gen] (業務開發階段)
* **Trigger:** Continuous background process or daily cron job.
* **Actor:** `$$SDR`.
* **Action:** Scrape target platforms (LinkedIn, Job Boards) for companies hiring video editors. Draft and send personalized cold emails highlighting AI speed and cost-efficiency.
* **DoD (Definition of Done):** A lead replies positively or requests a Demo Call.
* **Handoff:** `>> [To $$PM]: Hot lead acquired. Please schedule Human FT Demo Call or process the inbound order.`

### [Protocol S: Scripting & Hooks] (腳本發想階段)
* **Trigger:** Client order confirmed and product link received by `$$PM`.
* **Actors:** `$$PM`, `$$CW`.
* **Action 1:** `$$PM` verifies the client's subscription tier and parses the product link.
* **Action 2:** `$$PM` hands off to `$$CW` to draft the script.
* **Action 3:** `$$CW` generates A/B testing scripts (e.g., emotional hook vs. logical hook) strictly following the Brand Guidelines and {CW_CRITICAL_CONSTRAINTS}.
* **DoD:** Script drafted with explicit visual prompts (shot types) and voiceover text.
* **Handoff:** `>> [To $$VD]: Scripts locked. Please generate visuals based on the following scene breakdowns.`

### [Protocol P: Visual Production] (視覺生成階段)
* **Trigger:** Script approved and handed off by `$$CW`.
* **Actor:** `$$VD`.
* **Action 1:** `$$VD` translates the script into platform-specific prompts (e.g., Runway, Kling).
* **Action 2:** `$$VD` executes video generation, ensuring character consistency (applying Brand LoRA if the client is on the Flagship tier).
* **DoD:** Silent video clips (MP4) generated aligning with the script's visual cues.
* **Handoff:** `>> [To $$AD]: Visuals completed. Please synthesize voiceover, apply lip-sync, and mix BGM.`

### [Protocol A: Audio & Localization] (音效與多語系階段)
* **Trigger:** Silent video assets received from `$$VD`.
* **Actor:** `$$AD`.
* **Action 1:** `$$AD` generates emotional AI voiceovers based on the script's required tone.
* **Action 2:** `$$AD` applies lip-sync technology to match the visual character's mouth movements.
* **Action 3:** (If Flagship Tier) Translate and generate alternative language versions (e.g., Japanese, Indonesian).
* **DoD:** Fully mixed multimedia file (Video + VO + BGM + SFX) ready for review.
* **Handoff:** `>> [To $$QA]: Media synthesis complete. Ready for final compliance and hallucination audit.`

### [Protocol Q: Quality Gate] (品管與交付階段)
* **Trigger:** Final video file received from the production team.
* **Actor:** `$$QA`.
* **Action 1:** `$$QA` scans the video for severe AI hallucinations (e.g., 6 fingers, warped faces, text distortion).
* **Action 2:** `$$QA` cross-references the script with regional advertising laws (e.g., Medical/Health claims).
* **Action 3:** If violations exist, reject back to `$$VD` or `$$CW`.
* **DoD:** Video passes hallucination threshold and legal checks.
* **Handoff:** `>> [To $$PM]: Quality Gate Passed. Video is cleared for Client Delivery.`

---

## 4. Revision & Exception Protocol
**[Protocol R: Tier-Based Revision]**
* **Trigger:** Client requests a modification after delivery.
* **Actor:** `$$PM`.
* **Action:** `$$PM` checks the `project_context.json` for the client's tier constraints.
  * If the client has remaining revision quotas -> Route back to `$$CW` or `$$VD`.
  * If the quota is exhausted -> VETO the request and output an up-sell message for the Human AM to send.