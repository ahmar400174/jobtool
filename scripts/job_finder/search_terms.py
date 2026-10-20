"""Canonical queries so profession labels also work as job title searches."""
import re


def normalise_role(role):
    role = re.sub(r"[-\u2010-\u2015\u2212]", " ", role.lower())
    role = re.sub(r"\bfull\s*stack\b", "full stack", role)
    return " ".join(role.split())


def is_full_stack_ai_role(role):
    role = normalise_role(role)
    return "full stack" in role and bool(re.search(r"\b(?:ai|artificial intelligence|genai|llm|ml)\b", role))


def query_terms(keywords):
    result = []
    for role in keywords or ["QA Engineer"]:
        normal = normalise_role(role)
        variants = ["full stack AI engineer", "full stack engineer", "AI engineer"] if is_full_stack_ai_role(role) else {
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
