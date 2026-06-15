from pathlib import Path


def contract_fixture_path(name: str) -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = (
            parent
            / "packages"
            / "contracts"
            / "src"
            / "fixtures"
            / name
        )
        if candidate.is_file():
            return candidate
    return None
