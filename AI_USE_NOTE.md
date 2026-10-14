# AI use note

**How I used AI.** I used Claude to help me understand the assignment, plan the work, find and summarise public sources on EasySLR and the candidate firms, draft the first version of the research spreadsheet and evidence CSV format, review the tool's input files for errors, and draft the brief text.

**What I checked myself.** I opened the source URLs for the real-data Verified rows and marked them Y in `checked_by_you`. I found the sale of Source Health Economics to SCIRIS myself and corrected my "small independent firm" assumption. I ran the tool and its unit tests and read the output. Unknown and Interpretation rows are left with `checked_by_you` blank. The rows in the test files are fictional, so their Y marks don't mean I checked real sources.

**One suggestion I rejected.** The rule engine suggested "Defer" for Pharmacoevidence because of its in-house AI tool, which a published ISPOR poster shows it uses in a NICE submission. I kept that suggestion visible but overrode it in `data/overrides.csv` to "Discovery call candidate", with a written reason. I want to test whether they would use an external platform for review types their tool doesn't cover, or act as a channel for EasySLR.
