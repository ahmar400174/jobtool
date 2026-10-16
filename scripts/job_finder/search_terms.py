"""Canonical queries so profession labels also work as job title searches."""


def query_terms(keywords):
    result = []
    for role in keywords or ["QA Engineer"]:
        normal = " ".join(role.lower().split())
        variants = {
            "software engineering": ["software engineer", "software developer", "full stack developer"],
            "software development": ["software engineer", "software developer", "full stack developer"],
            "software": ["software engineer", "software developer", "full stack developer"],
            "quality assurance": ["QA Engineer", "SDET", "Test Engineer"],
        }.get(normal, [role])
        for term in variants:
            if term.lower() not in {r.lower() for r in result}:
                result.append(term)
    return result


def jobicy_terms(keywords):
    result = []
    for term in query_terms(keywords):
        lower = term.lower()
        tag = "software" if any(w in lower for w in ["software", "developer", "full stack"]) else "qa" if "qa" in lower or "quality assurance" in lower else term
        if tag not in result:
            result.append(tag)
    return result
