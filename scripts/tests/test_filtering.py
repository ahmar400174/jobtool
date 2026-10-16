"""
Unit tests for profession_matcher and filters.

Run with:
    python -m pytest scripts/tests/test_filtering.py -v
or from inside the scripts/ directory:
    python -m pytest tests/test_filtering.py -v
"""

from __future__ import annotations
import sys
from pathlib import Path

# Make sure job_finder package is importable when running tests from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from job_finder.models import JobListing
from job_finder.profession_matcher import score_job
from job_finder.sources.linkedin import _resolve_remote_label


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job(title: str, remote: str = "Remote", description: str = "") -> JobListing:
    return JobListing(
        title=title,
        company="Acme Corp",
        location="Remote" if remote == "Remote" else "New York, NY",
        remote=remote,
        posted="2026-09-01",
        url=f"https://example.com/{title.replace(' ', '-')}",
        source="LinkedIn",
        description=description,
    )


# ---------------------------------------------------------------------------
# Test 1 — QA Engineer + Remote → only remote QA jobs accepted
# ---------------------------------------------------------------------------

class TestQAEngineerRemote:

    ROLE = "QA Engineer"
    WP   = "remote"

    def test_qa_engineer_accepted(self):
        job = _job("QA Engineer", "Remote", "selenium playwright test cases")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Expected ACCEPTED but got REJECTED. Score={score} Reason={reason}"

    def test_qa_automation_engineer_accepted(self):
        """Test 4: QA Automation Engineer + Remote → ACCEPTED"""
        job = _job("QA Automation Engineer", "Remote", "cypress playwright automation")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Expected ACCEPTED. Score={score} Reason={reason}"

    def test_software_qa_engineer_accepted(self):
        job = _job("Software QA Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Expected ACCEPTED. Score={score} Reason={reason}"

    def test_sdet_accepted(self):
        job = _job("SDET", "Remote", "software development engineer in test automation")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Expected ACCEPTED. Score={score} Reason={reason}"

    # --- Wrong profession → must be rejected ---

    def test_software_engineer_rejected(self):
        """Test 2: Software Engineer must be REJECTED"""
        job = _job("Senior Software Engineer", "Remote", "selenium in ci pipeline")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_backend_engineer_rejected(self):
        job = _job("Backend Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_frontend_engineer_rejected(self):
        job = _job("Frontend Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_devops_engineer_rejected(self):
        job = _job("DevOps Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_data_engineer_rejected(self):
        job = _job("Data Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_ml_engineer_rejected(self):
        job = _job("Machine Learning Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    # --- Wrong workplace → must be rejected ---

    def test_qa_engineer_hybrid_rejected(self):
        """Test 3: QA Engineer + Hybrid → REJECTED"""
        job = _job("QA Engineer", "Hybrid")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED (hybrid). Score={score} Reason={reason}"

    def test_qa_engineer_onsite_rejected(self):
        job = _job("QA Engineer", "On-site")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED (on-site). Score={score} Reason={reason}"

    def test_qa_engineer_unknown_rejected(self):
        job = _job("QA Engineer", "Unknown")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED (unknown). Score={score} Reason={reason}"

    def test_sdet_onsite_philadelphia_rejected_no_api_filter(self):
        """When NOT using LinkedIn's remote filter (api_remote_filter=False),
        a city/state location like Philadelphia should resolve to Unknown
        and be rejected."""
        job = JobListing(
            title="Software Development Engineer in Test (SDET)",
            company="Comcast",
            location="Philadelphia, PA",
            remote="Unknown",      # _resolve_remote_label(loc, api_remote_filter=False) → Unknown
            posted="2026-09-10",
            url="https://linkedin.com/jobs/view/12345",
            source="LinkedIn",
            description="Looking for an SDET to work from our Philadelphia office. "
                        "Some remote flexibility may be available.",
        )
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, (
            f"SDET Philadelphia on-site job should be REJECTED. "
            f"Score={score} Reason={reason}"
        )

    def test_sdet_hybrid_rejected(self):
        """Even with f_WT=2, if location says Hybrid it must be rejected."""
        job = JobListing(
            title="Software Development Engineer in Test (SDET)",
            company="Comcast",
            location="Hybrid - Philadelphia, PA",
            remote="Hybrid",     # _resolve_remote_label("Hybrid - ...") → Hybrid
            posted="2026-09-10",
            url="https://linkedin.com/jobs/view/12346",
            source="LinkedIn",
            description="Hybrid SDET role.",
        )
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, (
            f"Hybrid SDET should be REJECTED. Score={score} Reason={reason}"
        )


# ---------------------------------------------------------------------------
# Test 5 — React Developer + Remote → only frontend/React jobs accepted
# ---------------------------------------------------------------------------

class TestReactDeveloperRemote:

    ROLE = "React Developer"
    WP   = "remote"

    def test_react_developer_accepted(self):
        job = _job("React Developer", "Remote", "react hooks redux nextjs frontend")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Expected ACCEPTED. Score={score} Reason={reason}"

    def test_frontend_react_developer_accepted(self):
        job = _job("Frontend React Developer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Expected ACCEPTED. Score={score} Reason={reason}"

    def test_generic_software_engineer_rejected(self):
        job = _job("Software Engineer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_java_developer_rejected(self):
        job = _job("Java Developer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"

    def test_python_developer_rejected(self):
        job = _job("Python Developer", "Remote")
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Expected REJECTED. Score={score} Reason={reason}"


# ---------------------------------------------------------------------------
# _resolve_remote_label (LinkedIn location field parsing)
# ---------------------------------------------------------------------------

class TestResolveRemoteLabel:

    # --- Without api_remote_filter (strict location-only) ---

    def test_remote(self):
        assert _resolve_remote_label("Remote") == "Remote"

    def test_remote_us(self):
        assert _resolve_remote_label("Remote - United States") == "Remote"

    def test_remote_worldwide(self):
        assert _resolve_remote_label("Remote - Worldwide") == "Remote"

    def test_hybrid(self):
        assert _resolve_remote_label("Hybrid") == "Hybrid"

    def test_new_york_no_filter(self):
        assert _resolve_remote_label("New York, NY") == "Unknown"

    def test_united_states_no_filter(self):
        assert _resolve_remote_label("United States") == "Unknown"

    def test_empty_no_filter(self):
        assert _resolve_remote_label("") == "Unknown"

    def test_wfh(self):
        assert _resolve_remote_label("Work From Home") == "Remote"

    # --- Strict Location Parsing Tests ---

    def test_city_state_returns_unknown(self):
        """City/state location without explicit Remote signal → Unknown (requires description proof)."""
        assert _resolve_remote_label("New York, NY", api_remote_filter=True) == "Unknown"

    def test_united_states_returns_unknown(self):
        assert _resolve_remote_label("United States", api_remote_filter=True) == "Unknown"

    def test_empty_returns_unknown(self):
        assert _resolve_remote_label("", api_remote_filter=True) == "Unknown"

    def test_hybrid_with_api_filter(self):
        assert _resolve_remote_label("Hybrid", api_remote_filter=True) == "Hybrid"

    def test_onsite_with_api_filter(self):
        assert _resolve_remote_label("On-site - Chicago, IL", api_remote_filter=True) == "On-site"


from job_finder.filters import normalize_remote_label


class TestFullDescriptionClassification:

    ROLE = "QA Engineer"
    WP   = "remote"

    def test_hybrid_description_rejected(self):
        """Job in Chicago with description stating 3 days in office → REJECTED"""
        job = JobListing(
            title="QA Engineer",
            company="FinTech Corp",
            location="Chicago, IL",
            remote="Unknown",
            posted="2026-09-12",
            url="https://linkedin.com/jobs/view/9991",
            source="LinkedIn",
            description="We are seeking a QA Engineer in Chicago. This role requires 3 days a week in office and 2 days remote.",
        )
        normalize_remote_label(job)
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"Hybrid job should be REJECTED. Score={score} Reason={reason}"

    def test_onsite_description_rejected(self):
        """Job in Boston with description stating on-site work required → REJECTED"""
        job = JobListing(
            title="QA Engineer",
            company="BioTech Inc",
            location="Boston, MA",
            remote="Unknown",
            posted="2026-09-12",
            url="https://linkedin.com/jobs/view/9992",
            source="LinkedIn",
            description="On-site position at our Boston headquarters. Must commute to office daily.",
        )
        normalize_remote_label(job)
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert not accepted, f"On-site job should be REJECTED. Score={score} Reason={reason}"

    def test_fully_remote_description_accepted(self):
        """Job in Dallas with description confirming 100% remote → ACCEPTED"""
        job = JobListing(
            title="QA Engineer",
            company="CloudScale",
            location="Dallas, TX",
            remote="Unknown",
            posted="2026-09-12",
            url="https://linkedin.com/jobs/view/9993",
            source="LinkedIn",
            description="100% remote role. Work from home position anywhere in the US.",
        )
        normalize_remote_label(job)
        score, reason, accepted = score_job(job, self.ROLE, self.WP)
        assert accepted, f"Fully remote job should be ACCEPTED. Score={score} Reason={reason}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
