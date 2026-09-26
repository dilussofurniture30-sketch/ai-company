AGENTS = {
    "manager": {"budget_monthly_usd": 50, "role": "Orchestrator"},
    "job_hunter": {"budget_monthly_usd": 25, "role": "Opportunity discovery"},
    "analyst": {"budget_monthly_usd": 25, "role": "Opportunity economics"},
    "developer": {"budget_monthly_usd": 100, "role": "Software"},
    "designer": {"budget_monthly_usd": 100, "role": "Design"},
    "writer": {"budget_monthly_usd": 50, "role": "Content"},
    "reviewer_1": {"budget_monthly_usd": 50, "role": "QA"},
    "reviewer_2": {"budget_monthly_usd": 50, "role": "Final QA"},
    "finance": {"budget_monthly_usd": 25, "role": "Unit economics"}
}

POLICY = {
    "external_actions_requiring_human_approval": [
        "submit_marketplace_proposal",
        "accept_contract",
        "send_external_message",
        "payment",
        "account_change",
        "delete_external_data"
    ],
    "marketplace_policy": "Use official APIs/integrations and follow each marketplace's terms."
}
