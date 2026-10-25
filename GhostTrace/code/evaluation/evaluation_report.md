# GhostTrace Evaluation Report

Evaluation against the **32 participant-provided labelled examples**, not the hidden evaluation set.

## Actual measured metrics

- cases: **32**
- status_correct: **29**
- status_accuracy: **0.90625**
- exact_sequence_correct: **8**
- exact_sequence_accuracy: **0.25**
- step_true: **193**
- step_pred: **159**
- step_exact_overlap: **155**
- step_precision: **0.974843**
- step_recall: **0.803109**
- index_aligned_field_accuracy: **0.699558**

Definitions: status accuracy is exact label matching; sequence accuracy requires exactly matching ordered step objects (excluding step_no, which is checked by schema validation). Step precision/recall use multisets of all six other fields, not fuzzy matches. Field accuracy aligns steps by array index and treats unmatched positions as incorrect. No hidden-label accuracy is claimed.

## Output contract

- Schema/ordering/evidence violations on samples: **0**

## Observed failures and root causes

- case_01: status INCOMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_001; observed .
- case_02: status INCOMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_002; observed .
- case_03: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_7566, VERIFY_RECORD_PRESENT:audit_record_2016, VERIFY_RECORD_ANONYMIZED:analytics_9406; observed VERIFY_RECORD_ABSENT:account_7566, VERIFY_RECORD_PRESENT:audit_record_2016.
- case_04: status INCOMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_004, VERIFY_RECORD_ANONYMIZED:analytics_901; observed .
- case_06: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:search_001, DELETE_RECORD:search_001, VERIFY_RECORD_ABSENT:account_006, VERIFY_RECORD_ABSENT:search_001; observed REPORT_REMAINING_RECORD:search_001, DELETE_RECORD:search_001, VERIFY_RECORD_ABSENT:search_001.
- case_07: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:support_001, DELETE_RECORD:support_001, VERIFY_RECORD_ABSENT:account_007, VERIFY_RECORD_ABSENT:support_001; observed REPORT_REMAINING_RECORD:support_001, DELETE_RECORD:support_001, VERIFY_RECORD_ABSENT:support_001.
- case_08: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:export_001, DELETE_RECORD:export_001, VERIFY_RECORD_ABSENT:account_008, VERIFY_RECORD_ABSENT:export_001; observed REPORT_REMAINING_RECORD:export_001, DELETE_RECORD:export_001, VERIFY_RECORD_ABSENT:export_001.
- case_09: status INCOMPLETE vs INCOMPLETE; expected REPORT_RESTORE_RISK:backup_4978, BLOCK_RESTORE:backup_4978, VERIFY_RECORD_ABSENT:account_3960, VERIFY_RECORD_PRESENT:audit_record_4902, VERIFY_RESTORE_BLOCKED:backup_4978; observed REPORT_RESTORE_RISK:backup_4978, BLOCK_RESTORE:backup_4978, VERIFY_RESTORE_BLOCKED:backup_4978.
- case_10: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:support_002, DELETE_RECORD:support_002, VERIFY_RECORD_ABSENT:account_010, VERIFY_RECORD_ABSENT:support_002; observed REPORT_REMAINING_RECORD:support_002, DELETE_RECORD:support_002, VERIFY_RECORD_ABSENT:support_002.
- case_17: status INCOMPLETE vs INCOMPLETE; expected REPORT_RESTORE_RISK:backup_3245, BLOCK_RESTORE:backup_3245, VERIFY_RECORD_ABSENT:account_4092, VERIFY_RECORD_PRESENT:audit_record_1797, VERIFY_RESTORE_BLOCKED:backup_3245; observed REPORT_RESTORE_RISK:backup_3245, BLOCK_RESTORE:backup_3245, VERIFY_RECORD_ABSENT:account_4092, VERIFY_RECORD_ABSENT:account_6523, VERIFY_RECORD_PRESENT:audit_record_1797, VERIFY_RESTORE_BLOCKED:backup_3245.
- case_18: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:search_4013, REPORT_EXPOSED_PII:analytics_037, REPORT_EXPOSED_PII:support_5569, REPORT_ACTIVE_DATA_FLOW:data_flow_4890, DISABLE_DATA_FLOW:data_flow_4890, DELETE_RECORD:search_4013, REDACT_RECORD:support_5569, ANONYMIZE_RECORD:analytics_037, VERIFY_RECORD_ABSENT:account_5521, VERIFY_RECORD_ABSENT:search_4013, VERIFY_RECORD_PRESENT:audit_record_6645, VERIFY_RECORD_REDACTED:support_5569, VERIFY_RECORD_ANONYMIZED:analytics_037, VERIFY_DATA_FLOW_DISABLED:data_flow_4890; observed REPORT_REMAINING_RECORD:search_4013, REPORT_EXPOSED_PII:analytics_037, REPORT_EXPOSED_PII:support_5569, REPORT_ACTIVE_DATA_FLOW:data_flow_4890, DISABLE_DATA_FLOW:data_flow_4890, DELETE_RECORD:search_4013, REDACT_RECORD:support_5569, ANONYMIZE_RECORD:analytics_037, VERIFY_RECORD_ABSENT:search_4013, VERIFY_RECORD_REDACTED:support_5569, VERIFY_RECORD_ANONYMIZED:analytics_037, VERIFY_DATA_FLOW_DISABLED:data_flow_4890.
- case_20: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:search_4262, REPORT_ACTIVE_DATA_FLOW:data_flow_1770, DISABLE_DATA_FLOW:data_flow_1770, DELETE_RECORD:search_4262, VERIFY_RECORD_ABSENT:account_5037, VERIFY_RECORD_ABSENT:search_4262, VERIFY_RECORD_PRESENT:audit_record_5569, VERIFY_DATA_FLOW_DISABLED:data_flow_1770; observed REPORT_REMAINING_RECORD:search_4262, REPORT_ACTIVE_DATA_FLOW:data_flow_1770, DISABLE_DATA_FLOW:data_flow_1770, DELETE_RECORD:search_4262, VERIFY_RECORD_ABSENT:search_4262, VERIFY_DATA_FLOW_DISABLED:data_flow_1770.
- case_21: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_6440, VERIFY_RECORD_PRESENT:audit_record_3737, VERIFY_RECORD_ANONYMIZED:analytics_5335; observed VERIFY_RECORD_PRESENT:audit_record_3737.
- case_22: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:search_8911, REPORT_EXPOSED_PII:analytics_4440, DELETE_RECORD:search_8911, ANONYMIZE_RECORD:analytics_4440, VERIFY_RECORD_ABSENT:account_4990, VERIFY_RECORD_ABSENT:search_8911, VERIFY_RECORD_PRESENT:audit_record_3482, VERIFY_RECORD_ANONYMIZED:analytics_4440; observed REPORT_REMAINING_RECORD:search_8911, REPORT_EXPOSED_PII:analytics_4440, DELETE_RECORD:search_8911, ANONYMIZE_RECORD:analytics_4440, VERIFY_RECORD_ABSENT:search_8911, VERIFY_RECORD_PRESENT:audit_record_3482, VERIFY_RECORD_ANONYMIZED:analytics_4440.
- case_23: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:export_7364, REPORT_REMAINING_RECORD:search_898, DELETE_RECORD:export_7364, DELETE_RECORD:search_898, VERIFY_RECORD_ABSENT:account_410, VERIFY_RECORD_ABSENT:export_7364, VERIFY_RECORD_ABSENT:search_898, VERIFY_RECORD_PRESENT:audit_record_4128; observed REPORT_REMAINING_RECORD:export_7364, REPORT_REMAINING_RECORD:search_898, DELETE_RECORD:export_7364, DELETE_RECORD:search_898, VERIFY_RECORD_ABSENT:export_7364, VERIFY_RECORD_ABSENT:search_898.
- case_24: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:account_5334, REPORT_REMAINING_RECORD:search_5577, DELETE_RECORD:account_5334, DELETE_RECORD:search_5577, VERIFY_RECORD_ABSENT:account_5334, VERIFY_RECORD_ABSENT:search_5577, VERIFY_RECORD_PRESENT:audit_record_7095; observed REPORT_REMAINING_RECORD:account_5334, REPORT_REMAINING_RECORD:search_5577, DELETE_RECORD:account_5334, DELETE_RECORD:search_5577, VERIFY_RECORD_ABSENT:account_5334, VERIFY_RECORD_ABSENT:search_5577.
- case_25: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_3136, VERIFY_RECORD_PRESENT:audit_record_451, VERIFY_RECORD_ANONYMIZED:analytics_1895; observed VERIFY_RECORD_PRESENT:audit_record_451.
- case_26: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_5684, VERIFY_RECORD_PRESENT:audit_record_5416, VERIFY_RECORD_REDACTED:support_4715, VERIFY_RECORD_ANONYMIZED:analytics_4566, VERIFY_DATA_FLOW_DISABLED:data_flow_6244, VERIFY_RESTORE_BLOCKED:backup_3120; observed VERIFY_RECORD_PRESENT:audit_record_5416, VERIFY_RECORD_REDACTED:support_4715, VERIFY_DATA_FLOW_DISABLED:data_flow_6244, VERIFY_RESTORE_BLOCKED:backup_3120.
- case_27: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_3866, VERIFY_RECORD_PRESENT:audit_record_3830, VERIFY_RECORD_REDACTED:support_4707, VERIFY_RECORD_ANONYMIZED:analytics_4574, VERIFY_DATA_FLOW_DISABLED:data_flow_2295, VERIFY_RESTORE_BLOCKED:backup_5970; observed VERIFY_RECORD_PRESENT:audit_record_3830, VERIFY_RECORD_REDACTED:support_4707, VERIFY_DATA_FLOW_DISABLED:data_flow_2295, VERIFY_RESTORE_BLOCKED:backup_5970.
- case_28: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_5482, VERIFY_RECORD_PRESENT:audit_record_9265, VERIFY_RECORD_REDACTED:support_2351, VERIFY_RECORD_ANONYMIZED:analytics_6077, VERIFY_DATA_FLOW_DISABLED:data_flow_2337, VERIFY_RESTORE_BLOCKED:backup_838; observed VERIFY_RECORD_PRESENT:audit_record_9265, VERIFY_RECORD_REDACTED:support_2351, VERIFY_DATA_FLOW_DISABLED:data_flow_2337, VERIFY_RESTORE_BLOCKED:backup_838.
- case_29: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:search_1993, REPORT_EXPOSED_PII:analytics_5208, REPORT_EXPOSED_PII:support_5281, REPORT_ACTIVE_DATA_FLOW:data_flow_3827, DISABLE_DATA_FLOW:data_flow_3827, DELETE_RECORD:search_1993, REDACT_RECORD:support_5281, ANONYMIZE_RECORD:analytics_5208, VERIFY_RECORD_ABSENT:account_7012, VERIFY_RECORD_ABSENT:search_1993, VERIFY_RECORD_PRESENT:audit_record_3954, VERIFY_RECORD_REDACTED:support_5281, VERIFY_RECORD_ANONYMIZED:analytics_5208, VERIFY_DATA_FLOW_DISABLED:data_flow_3827; observed REPORT_REMAINING_RECORD:search_1993, REPORT_EXPOSED_PII:analytics_5208, REPORT_EXPOSED_PII:support_5281, REPORT_ACTIVE_DATA_FLOW:data_flow_3827, DISABLE_DATA_FLOW:data_flow_3827, DELETE_RECORD:search_1993, REDACT_RECORD:support_5281, ANONYMIZE_RECORD:analytics_5208, VERIFY_RECORD_ABSENT:search_1993, VERIFY_RECORD_REDACTED:support_5281, VERIFY_RECORD_ANONYMIZED:analytics_5208, VERIFY_DATA_FLOW_DISABLED:data_flow_3827.
- case_30: status INCOMPLETE vs INCOMPLETE; expected REPORT_REMAINING_RECORD:search_9359, REPORT_EXPOSED_PII:analytics_3697, REPORT_EXPOSED_PII:support_6477, REPORT_ACTIVE_DATA_FLOW:data_flow_8524, DISABLE_DATA_FLOW:data_flow_8524, DELETE_RECORD:search_9359, REDACT_RECORD:support_6477, ANONYMIZE_RECORD:analytics_3697, VERIFY_RECORD_ABSENT:account_4163, VERIFY_RECORD_ABSENT:search_9359, VERIFY_RECORD_PRESENT:audit_record_1707, VERIFY_RECORD_REDACTED:support_6477, VERIFY_RECORD_ANONYMIZED:analytics_3697, VERIFY_DATA_FLOW_DISABLED:data_flow_8524; observed REPORT_REMAINING_RECORD:search_9359, REPORT_EXPOSED_PII:analytics_3697, REPORT_EXPOSED_PII:support_6477, REPORT_ACTIVE_DATA_FLOW:data_flow_8524, DISABLE_DATA_FLOW:data_flow_8524, DELETE_RECORD:search_9359, REDACT_RECORD:support_6477, ANONYMIZE_RECORD:analytics_3697, VERIFY_RECORD_ABSENT:search_9359, VERIFY_RECORD_REDACTED:support_6477, VERIFY_RECORD_ANONYMIZED:analytics_3697, VERIFY_DATA_FLOW_DISABLED:data_flow_8524.
- case_31: status COMPLETE vs COMPLETE; expected VERIFY_RECORD_ABSENT:account_4857, VERIFY_RECORD_PRESENT:audit_record_6909, VERIFY_RECORD_REDACTED:tombstone_440; observed VERIFY_RECORD_PRESENT:audit_record_6909, VERIFY_RECORD_REDACTED:tombstone_440.
- case_32: status INCOMPLETE vs INCOMPLETE; expected REPORT_EXPOSED_PII:tombstone_9178, REDACT_RECORD:tombstone_9178, VERIFY_RECORD_ABSENT:account_8858, VERIFY_RECORD_PRESENT:audit_record_7068, VERIFY_RECORD_REDACTED:tombstone_9178; observed REPORT_EXPOSED_PII:tombstone_9178, REDACT_RECORD:tombstone_9178, VERIFY_RECORD_PRESENT:audit_record_7068, VERIFY_RECORD_REDACTED:tombstone_9178.

## Three additional adversarial evaluations (design contracts)

1. False COMPLETE dashboard: reported_status=COMPLETE is ignored when a verified matching present replica record exists. Expected INCOMPLETE with delete finding/remediation/check.
2. Historical alias: old email mapped through user_audit_log must identify the same user and still detect a secondary-store record under that alias.
3. Active restore: a backup with restore_allowed=true must produce REPORT_RESTORE_RISK, BLOCK_RESTORE, VERIFY_RESTORE_BLOCKED even if the primary account is absent.
These are documented adversarial scenarios; no pass claim is made without executing tests.

## Limitations

The baseline extractor does not natively read image pixels; PDF text extraction requires pdftotext. A missing source or unresolved identity never proves absence. Model usage is zero in this baseline and is reported separately. Accuracy on the labelled sample may differ from hidden evaluation.

## Full evaluation set

Generated prediction row count and schema validity are checked separately. Hidden canonical labels are not accessible, so hidden accuracy is not measured.
