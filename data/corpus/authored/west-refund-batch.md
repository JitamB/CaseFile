---
doc_id: west-refund-batch
table: crm.opportunity_note
account: ACC-0053
date: 2026-03-23
role: signal
driver: null
---
Raised the credit note for the duplicate billing run. The March cycle was invoiced
twice for this account after the failed retry on the 3rd, and finance have issued a
single credit for the full duplicate rather than reversing line by line. It will
land in the March ledger and it is large enough that the regional revenue number
for the month will look wrong until somebody reads the reason code.
