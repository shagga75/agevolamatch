from __future__ import annotations

from pathlib import Path

import yaml

from agevolamatch.models.company_profile import CompanyProfile


def load_company_profile(path: Path) -> CompanyProfile:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CompanyProfile.model_validate(data)
