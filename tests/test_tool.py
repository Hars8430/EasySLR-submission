"""Run from the project folder:  python3 -m unittest discover tests -v"""
import csv, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import accounts_tool as t

D = os.path.join(os.path.dirname(__file__), "..", "data")


def run(prefix):
    out = tempfile.NamedTemporaryFile(suffix=".csv", delete=False).name
    recs = t.run(f"{D}/{prefix}accounts.csv", f"{D}/{prefix}evidence.csv",
                 f"{D}/{prefix}overrides.csv", out)
    return {r["account"]: r for r in recs}, out


class RealData(unittest.TestCase):
    def test_actions(self):
        r, _ = run("")
        self.assertEqual(r["Evalueserve"]["suggested_action"], "Exclude")
        self.assertEqual(r["Costello Medical"]["suggested_action"], "Defer")
        self.assertEqual(r["Maven"]["suggested_action"], "Research more")
        self.assertEqual(r["Pharmacoevidence"]["suggested_action"], "Defer")
        self.assertEqual(r["Pharmacoevidence"]["final_action"], "Discovery call candidate")

    def test_tag_counts_match_evidence(self):
        r, _ = run("")
        self.assertEqual(r["Maven"]["unknown_count"], 3)


class TestCases(unittest.TestCase):
    def setUp(self):
        self.r, self.out = run("test_")

    def test_duplicates(self):
        self.assertEqual(self.r["Northwind Outcomes Research Ltd"]["suggested_action"], "Resolve duplicate")
        self.assertIn("same domain", self.r["Northwind Outcomes Research Limited"]["flags"])
        self.assertIn("similar name", self.r["Pharmaco Evidence Pvt Ltd"]["flags"])

    def test_missing_evidence(self):
        h = self.r["Harbour Evidence Partners"]
        self.assertEqual(h["suggested_action"], "Research more")
        self.assertIn("without a source URL", h["flags"])
        self.assertIn("unknown (looked, not found)", h["flags"])

    def test_conflict(self):
        b = self.r["Beacon HEOR"]
        self.assertEqual(b["suggested_action"], "Resolve conflict")
        self.assertIn("22 vs 150", b["flags"])

    def test_override_wins_and_keeps_suggestion(self):
        q = self.r["Quayside Health Economics"]
        self.assertEqual(q["suggested_action"], "Discovery call candidate")
        self.assertEqual(q["final_action"], "Defer")
        self.assertEqual(q["needs_human_review"], "Y")

    def test_csv_has_all_columns(self):
        with open(self.out) as f:
            self.assertEqual(csv.DictReader(f).fieldnames, t.COLUMNS)


class Helpers(unittest.TestCase):
    def test_name_normalisation(self):
        self.assertEqual(t.normalise_name("Pharmaco-Evidence Pvt. Ltd."), "pharmacoevidence")

    def test_domain_normalisation(self):
        self.assertEqual(t.normalise_domain("https://www.IconPLC.com/x"), "iconplc.com")

    def test_bad_tag_is_rejected(self):
        with self.assertRaises(SystemExit):
            t.check_tags([{"account": "X", "tag": "Fact"}])

    def test_bad_override_is_rejected(self):
        with self.assertRaises(SystemExit):
            t.apply_overrides([{"account": "A", "_has_flags": False, "suggested_action": "Defer"}],
                              [{"account": "A", "override_action": "Call them", "reason": "x"}])


if __name__ == "__main__":
    unittest.main()
