# Reflection: AI coding interactions

Each of us logs at least three meaningful AI coding interactions, including at
least one real problem and how we fixed it. Fill in an entry right after each one.

## Branda Heng — Role A

**Pending for Section 9C.** Complete three entries, including one that describes a real problem and how you fixed it.

### Interaction 1: <short title> (name, date)
- What I wanted:
- What I asked:
- What happened:
- What I did next:

## Carter McDonald — Role B

The “What I asked” sections paraphrase the prompts.

### Interaction 1 — Testing object detection locally

**What I wanted**

I wanted to see whether we could scan a drawer photo on a normal laptop without asking the instructor to sign up for an AI service or get an API key.

**What I asked**

I asked ChatGPT to walk me through setting up OWL-ViT locally and building a standalone script that could scan two sample photos, print the suggested items and scores, and record scan times.

**What happened**

AI provided a model setup script and a test script. My first cleaning-drawer run suggested a tape measure that wasn’t there. The label list also didn’t include the cleaning products I wanted the model to find.

**What I did next**

I expanded the label list, retook the sample photos, and compared the results at different thresholds. At 0.12, both photos produced useful suggestions, and both warm scans finished in under a second on my machine. I also recorded the false positives and missed items. That helped me decide what the model should do in the app. It gives users a starting list they can correct before saving.

### Interaction 2 — Turning the prototype into a reusable detector

**What I wanted**

I wanted my teammate to be able to call the detector from Flask without depending on the command-line script I used on Day 1.

**What I asked**

I asked Codex to move the working inference code into a reusable `scan(image_bytes)` function, put the labels and threshold in a config file, reuse the local model across scans, and return a consistent response for successful scans and failure states.

**What happened**

Codex created the detector module and a standalone check that ran both sample photos through the new function. The check returned the same nine suggestions in the same order as Day 1, with scores matching at the displayed precision.

**What I did next**

I ran the check myself in PowerShell and compared the output with my saved Day 1 results. I also noticed that my teammate’s app lived under `home-inventory/`, so I had Codex move my files to match that layout and updated the handoff with the correct commands. The comparison gave me a way to verify that reorganizing the code preserved what the detector returned.

### Interaction 3 — Fixing edits lost during slow saves and scans (Day 4)

**What I wanted**

I wanted to verify that the editor behaved correctly while a save or photo scan was still running, especially if the user kept making changes.

**What I asked**

I asked Codex to review the save and scan flows, reproduce the reported issues by delaying browser responses, and make a focused fix. I also asked it to check that normal saves and scans still worked afterward.

**What happened**

Codex reproduced two problems. A late save response could overwrite edits made after the user clicked Save. A late scan response could add suggestions after the user cleared or replaced the photo or opened another location. Codex changed `app.js` so newer edits stay visible and marked unsaved, a follow-up save updates the original location, and the editor ignores stale scan results.

**What I did next**

I independently repeated the delayed-response checks in the browser and ran the standard walkthrough. I verified that I could save the same item in two locations, restart Flask, find both with a mixed-case search, and remove the item from one location so only the other appeared in search. This showed me why a normal walkthrough can miss a bug. The problem only appeared when I interacted with the editor before the server finished responding.
