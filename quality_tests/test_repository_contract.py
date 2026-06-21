from __future__ import annotations

from pathlib import Path
import unittest


class RepositoryLayoutContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]

    def test_required_top_level_directories_exist(self) -> None:
        required_directories = (
            "docs",
            "firmware",
            "pc_simulator",
            "quality_tests",
            "scripts",
            "shared",
        )

        for directory_name in required_directories:
            with self.subTest(directory=directory_name):
                directory_path = self.repo_root / directory_name
                self.assertTrue(
                    directory_path.is_dir(),
                    f"Expected top-level directory to exist: {directory_path}",
                )

    def test_readme_exists_as_file(self) -> None:
        readme_path = self.repo_root / "README.md"

        self.assertTrue(
            readme_path.is_file(),
            f"Expected top-level README.md file to exist: {readme_path}",
        )

    def test_modeling_contract_directories_exist(self) -> None:
        required_directories = (
            self.repo_root / "docs" / "modeling",
            self.repo_root / "shared" / "contracts",
            self.repo_root / "quality_tests" / "model_contract",
        )

        for directory_path in required_directories:
            with self.subTest(directory=directory_path):
                self.assertTrue(
                    directory_path.is_dir(),
                    f"Expected modeling contract directory to exist: {directory_path}",
                )


if __name__ == "__main__":
    unittest.main()
