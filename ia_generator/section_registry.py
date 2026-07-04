# A mapping of workspace types to a list of allowed section_ids
WORKSPACE_SECTIONS = {
    "disease": [
        "overview", "symptoms", "diagnosis", "criteria_detail", 
        "treatment", "pathophysiology", "complications", 
        "epidemiology", "prognosis", "references"
    ],
    "drug": [
        "overview", "mechanism", "indications", "dosage",
        "side_effects", "contraindications", "interactions", "references"
    ],
    "case": [
        "presentation", "findings", "differential", 
        "diagnosis", "management", "references"
    ],
    "comparison": [
        "overview", "table", "differences", "references"
    ],
    "algorithm": [
        "overview", "step"
    ],
    "lab_test": [
        "overview", "high", "low", "significance", "related"
    ],
    "anatomy": [
        "overview"
    ],
    "procedure": [
        "overview"
    ],
    "menu": [
        "main_menu"
    ]
}

def get_allowed_sections(workspace_type: str) -> list[str]:
    return WORKSPACE_SECTIONS.get(workspace_type, ["overview"])
