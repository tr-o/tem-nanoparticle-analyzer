import unittest
from pathlib import Path

from tem_analyzer.cli import ROOT, PIPELINES, main


class CLIContractTest(unittest.TestCase):
    def test_repository_root(self):
        self.assertEqual(ROOT, Path(__file__).resolve().parents[1])
    def test_paths(self):
        self.assertEqual(PIPELINES, ROOT / "experiments")
    def test_help(self):
        with self.assertRaises(SystemExit) as error:
            main(["--help"])
        self.assertEqual(error.exception.code, 0)
    def test_doctor(self):
        self.assertEqual(main(["doctor"]), 0)


if __name__ == "__main__":
    unittest.main()
