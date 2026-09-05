from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


from surface_atlas import report_builder as BUILDER, report_presentation as PRESENTATION, report_workflows as WORKFLOWS
SCRIPTS = Path(BUILDER.__file__).parent


class Node:
    def __init__(self, tag="root", attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def text(self):
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find(self, tag=None, **attrs):
        found = []
        if (tag is None or self.tag == tag) and all(self.attrs.get(k) == v for k, v in attrs.items()):
            found.append(self)
        for child in self.children:
            if isinstance(child, Node):
                found.extend(child.find(tag, **attrs))
        return found


class ParsedHTML(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(markup):
    return ParsedHTML(markup).root


def target(**updates):
    record = {
        "target_id": "T-ALT-001", "preferred_name": "Alternate receptor",
        "structure_tier": "survey-2027", "evidence_score": {"score": None},
        "risk": {"observed_signal_score": None, "unresolved_dimensions": ["surface abundance"]},
    }
    record.update(updates)
    return record


def screen(identifier, **updates):
    record = {
        "screening_id": identifier, "molecule_id": identifier, "molecule_name": identifier,
        "run_id": "alternate-run", "target_id": "T-ALT-001", "site_id": "SITE-ONE",
        "scoring_function": "test-score", "score_units": "arbitrary units",
        "route": "local-test-route", "model_version": "model-v1", "screen_role": "prospective",
        "execution_state": "completed", "pose_score": -4.5,
        "seed_agreement": {"state": "not-assessed", "successful_comparable_seed_count": 1, "top_score_span_kcal_mol": 0},
        "seed_observations": [{"parameters": {"exhaustiveness": 8}}],
    }
    record.update(updates)
    return record


class PresentationProjectionTests(unittest.TestCase):
    def test_expression_uses_recorded_population_and_keeps_zero(self):
        record = target(expression_context={
            "population_key": "activated_cells", "population_label": "Activated cells", "cohort_name": "Example cohort",
            "single_cell_percent_expressing": {"values": {"activated_cells": 0, "resting_cells": 12}},
        })
        doc = parse(PRESENTATION.render_dossier_context(BUILDER, record))
        self.assertIn("Activated cells expressing", doc.text())
        self.assertIn("0%", doc.text())
        self.assertIn("Example cohort", doc.text())
        self.assertNotIn("Tumor", doc.text())
        _, _, value, label, cohort = PRESENTATION.expression_summary(record)
        self.assertEqual((value, label, cohort), (0, "Activated cells", "Example cohort"))

    def test_missing_expression_does_not_introduce_a_disease_specific_metric(self):
        doc = parse(PRESENTATION.render_dossier_context(BUILDER, target()))
        self.assertNotIn("Tumor", doc.text())
        self.assertNotIn("cells expressing", doc.text())

    def test_expression_population_label_is_escaped(self):
        record = target(expression_context={"population_label": '<img src=x>',
                        "single_cell_percent_expressing": {"values": {"disease_cells": 5}}})
        doc = parse(PRESENTATION.render_dossier_context(BUILDER, record))
        self.assertEqual(doc.find("img"), [])
        self.assertIn("<img src=x> expressing", doc.text())

    def overview(self, **updates):
        args = dict(plan={"disease": {"name": "Alternate autoimmune disease"}}, ledger={}, collections={},
                    binders=[], artifact_map={}, generated_at="2027-01-02T03:04:05Z")
        args.update(updates)
        return PRESENTATION.narrative_overview(BUILDER, **args)

    def test_empty_atlas_does_not_claim_census_completion_or_execution(self):
        doc = parse(self.overview())
        self.assertEqual(len(doc.find("section", **{"class": "cover cover-text-only"})), 1)
        self.assertEqual(doc.find("h1")[0].text(), "Alternate autoimmune disease")
        self.assertNotIn("Every entity has a disposition", doc.text())
        self.assertIn("No normalized screening records are included", doc.text())
        self.assertNotIn("no provider jobs have run", doc.text())
        for demo_specific in ("PRIVATE-CASE-EXAMPLE", "INTERNAL-RUN-EXAMPLE"):
            self.assertNotIn(demo_specific, doc.text())

    def test_complete_accounting_requires_observed_validation_flag(self):
        pending = {"discovered-entities.json": [{"entity_id": "E-1", "surface_disposition": "pending"}]}
        self.assertNotIn("Target counts after review", self.overview(collections=pending))
        validated = self.overview(ledger={"_report_state": {"census_accounting_validated": True}})
        self.assertIn("Target counts after review", validated)

    def test_overview_uses_current_report_hierarchy_without_rejected_copy(self):
        doc = parse(self.overview())
        text = doc.text()
        self.assertIn("Cell-surface target research", text)
        self.assertIn("Compare surface targets, binding sites, and candidate results.", text)
        self.assertNotIn("Evidence types", text)
        self.assertIn("Explore the records", text)
        for rejected in ("A clear boundary at every step", "Define the question"):
            self.assertNotIn(rejected, text)

    def test_arbitrary_tier_is_filterable_and_legend_does_not_invent_waves(self):
        profile = BUILDER.target_profile(target(), 0)
        doc = parse(PRESENTATION.render_explorer(BUILDER, [profile]))
        options = doc.find("select", id="atlas-tier")[0].find("option")
        self.assertEqual([option.attrs["value"] for option in options], ["", "survey-2027"])
        legend = doc.find("div", **{"class": "plot-legend"})
        if legend:
            self.assertIn("survey-2027", legend[0].text())
            self.assertNotIn("Wave A", legend[0].text())

    def test_predicted_figure_uses_its_own_identity_and_provenance(self):
        image = {"structure_id": "S-ALT-PREDICTED", "accession": "ALT-MODEL-42",
                 "evidence_class": "predicted complex", "artifacts": [{"path": "renders/alt.png", "role": "structure-render"}]}
        doc = parse(self.overview(collections={"structures.json": [image]}, artifact_map={"renders/alt.png": "artifacts/alt.png"}))
        figure = doc.find("figure")[0]
        self.assertIn("ALT-MODEL-42", figure.text())
        self.assertIn("predicted complex", figure.text())
        self.assertNotIn("Deposited reference", figure.text())
        self.assertEqual(figure.find("a")[0].attrs["href"], "structures.html#structure-s-alt-predicted")
        self.assertEqual(figure.find("img")[0].attrs["src"], "artifacts/alt.png")

    def test_html_text_cannot_create_executable_elements(self):
        payload = '<img src=x onerror="alert(1)"> & "example"'
        doc = parse(self.overview(plan={"disease": {"name": payload}}, generated_at=payload))
        self.assertEqual(doc.find("h1")[0].text(), payload)
        self.assertEqual(doc.find("img"), [])
        self.assertEqual(doc.find("script"), [])

    def test_explorer_json_round_trips_script_closing_payload_as_data(self):
        payload = '</script><script>alert("x")</script>& <surface>'
        record = target(preferred_name=payload, structure_tier='custom"><img src=x>')
        doc = parse(PRESENTATION.render_explorer(BUILDER, [BUILDER.target_profile(record, 0)]))
        scripts = doc.find("script")
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0].attrs["type"], "application/json")
        self.assertEqual(json.loads(scripts[0].text())[0]["name"], payload)
        self.assertEqual(doc.find("img"), [])

    def test_optional_score_details_accept_only_object_records(self):
        for value in (None, "unavailable", {"points": 1}, [None, "unavailable", {"points": 0}]):
            record = target(evidence_score={"components": value}, risk={"observed_signals": value})
            original = copy.deepcopy(record)
            projected = PRESENTATION.explorer_records([BUILDER.target_profile(record, 0)])[0]
            expected = [{"points": 0}] if isinstance(value, list) else []
            self.assertEqual(projected["evidenceComponents"], expected)
            self.assertEqual(projected["warningSignals"], expected)
            self.assertEqual(record, original)

    def test_projection_preserves_null_and_zero_as_distinct_values(self):
        records = [target(), target(target_id="T-ZERO", evidence_score={"score": 0, "components": [{"component": "direct", "points": 0}]},
                                    risk={"observed_signal_score": 0, "observed_signals": [{"signal": "example", "points": 0}]},
                                    cancer_surfaceome_context={"single_cell_percent_expressing": {"values": {"tumor": 0}}})]
        original = copy.deepcopy(records)
        projected = PRESENTATION.explorer_records([BUILDER.target_profile(r, i) for i, r in enumerate(records)])
        for field in ("evidence", "risk", "tumor"):
            self.assertIsNone(projected[0][field])
            self.assertEqual(projected[1][field], 0)
        self.assertEqual(projected[1]["evidenceComponents"], records[1]["evidence_score"]["components"])
        self.assertEqual(projected[1]["warningSignals"], records[1]["risk"]["observed_signals"])
        self.assertEqual(records, original)
        self.assertEqual(PRESENTATION.fmt(0), "0")
        for missing in (None, False, float("nan"), float("inf")):
            self.assertEqual(PRESENTATION.fmt(missing), "Not measured")
        doc = parse(PRESENTATION.render_dossier_context(BUILDER, records[1]))
        self.assertIn("0%", [node.text() for node in doc.find("strong")])


class ScreeningReadoutTests(unittest.TestCase):
    def render(self, records):
        return parse(PRESENTATION.render_screen_readout(BUILDER, records, {}, [BUILDER.target_profile(target(), 0)]))

    def test_single_seed_zero_span_is_not_presented_as_repeatability(self):
        doc = self.render([screen("M-ONE")])
        self.assertIn("Primary prospective screen", doc.text())
        self.assertIn("Alternate receptor · test-score", doc.text())
        self.assertIn("alternate-run · SITE-ONE", doc.text())
        self.assertIn("Molecules awaiting repeat runs", doc.text())
        rows = doc.find("tbody")[0].find("tr")
        self.assertIn("repeatability not assessed", rows[0].text().lower())
        self.assertIn("zero score span is not evidence of seed agreement", doc.text())
        self.assertNotIn("span 0", rows[0].text().lower())

    def test_control_failures_and_protocol_settings_remain_visible(self):
        canary = screen("CONTROL-CANARY", screen_role="positive-control", pose_score=0,
                        seed_observations=[{"parameters": {"exhaustiveness": 4}}])
        failed = screen("CONTROL-FAILED", screen_role="noncognate-control", execution_state="failed", pose_score=None,
                        failure_reason="conversion did not preserve atoms", seed_observations=[{"parameters": {"exhaustiveness": 32}}])
        doc = self.render([screen("M-PROSPECTIVE"), canary, failed])
        tables = doc.find("table")
        control_table = next(t for t in tables if "CONTROL-CANARY" in t.text())
        self.assertIn("CONTROL-FAILED", control_table.text())
        self.assertNotIn("M-PROSPECTIVE", control_table.text())
        rows = control_table.find("tbody")[0].find("tr")
        first, second = [[cell.text() for cell in row.find("td")] for row in rows]
        self.assertIn("0", first)
        self.assertIn("4", first)
        self.assertIn("No score recorded", second)
        self.assertIn("conversion did not preserve atoms", control_table.text())
        self.assertIn("32", second)
        self.assertIn("failed", " ".join(second).lower())
        self.assertIn("test-score", doc.text())
        self.assertIn("arbitrary units", doc.text())

    def test_distinct_scoring_contexts_have_unique_table_control_ids(self):
        records = [screen("M-A"), screen("M-B", site_id="SITE-TWO"), screen("M-C", scoring_function="other-score")]
        doc = self.render(records)
        tables = doc.find("table")
        self.assertEqual(len(tables), 3)
        ids = [table.attrs["id"] for table in tables]
        self.assertEqual(len(ids), len(set(ids)), "Different screen groups must not share table IDs")
        for table in tables:
            table_id = table.attrs["id"]
            self.assertEqual(len(doc.find("input", **{"data-table-filter": table_id})), 1)

    def test_different_model_versions_do_not_share_one_protocol_disclosure(self):
        doc = self.render([screen("M-V1"), screen("M-V2", model_version="model-v2")])
        disclosures = [node for node in doc.find("details") if "Protocol" in node.text()]
        self.assertEqual(len(disclosures), 2)
        self.assertTrue(any("model-v1" in node.text() for node in disclosures))
        self.assertTrue(any("model-v2" in node.text() for node in disclosures))


class OpportunityPresentationTests(unittest.TestCase):
    def test_nested_site_is_compact_and_full_mapping_is_collapsed(self):
        site = {"site_id": "SITE-ALTERNATE", "mode": "reference-interface",
                "evidence_class": "experimental-reference-binder-interface",
                "evidence": "Observed target-partner contacts", "numbering_scheme": "author-to-campaign",
                "residues": [{"campaign_chain_id": "B", "campaign_residue_number": 71,
                              "author_residue_number": "183", "insertion_code": None}],
                "excluded_regions": ["deposited partner"], "uncertain_regions": ["glycan occupancy"]}
        record = {"opportunity_id": "O-ALTERNATE", "target_id": "T-ALT-001", "molecular_job": "block",
                  "selected_format": "miniprotein", "modality": "fallback-format", "site": site,
                  "desired_effect": "Recover reference geometry", "rationale": "Inspect a defined interface",
                  "principal_risks": ["Unknown affinity", "Normal exposure not measured"],
                  "result_ingestion": {"state": "ready-awaiting-provider-results"}, "next_step": "Evaluate reference controls"}
        original = copy.deepcopy(record)
        doc = parse(BUILDER.render_opportunities([record]))
        article = doc.find("article")[0]
        visible_fields = next(child for child in article.children if isinstance(child, Node) and child.tag == "dl")
        values = dict(zip((n.text() for n in visible_fields.find("dt")), (n.text() for n in visible_fields.find("dd"))))
        self.assertEqual(values["Site"], "SITE-ALTERNATE")
        self.assertEqual(values["Format"], "miniprotein")
        self.assertEqual(values["Desired effect"], "Recover reference geometry")
        self.assertEqual(values["Result ingestion"], "ready-awaiting-provider-results")
        self.assertNotIn("campaign_residue_number", visible_fields.text())
        risks = next(child for child in article.children if isinstance(child, Node) and child.tag == "ul")
        self.assertEqual([node.text() for node in risks.find("li")], record["principal_risks"])
        details = article.find("details")[0]
        self.assertNotIn("open", details.attrs)
        self.assertEqual(json.loads(details.find("pre")[0].text()), site)
        self.assertEqual(record, original)

    def test_opportunity_text_and_nested_mapping_are_escaped_without_data_loss(self):
        payload = '</pre><script>alert("x")</script>& <img src=x>'
        site = {"site_id": payload, "evidence": payload, "residues": [{"insertion_code": None, "note": payload}]}
        record = {"opportunity_id": payload, "target_name": payload, "molecular_job": payload,
                  "selected_format": payload, "site": site, "rationale": payload,
                  "principal_risks": [payload], "next_step": payload,
                  "result_ingestion": {"state": payload}}
        doc = parse(BUILDER.render_opportunities([record]))
        self.assertEqual(doc.find("script"), [])
        self.assertEqual(doc.find("img"), [])
        self.assertEqual(len(doc.find("pre")), 1)
        self.assertEqual(json.loads(doc.find("pre")[0].text()), site)
        self.assertEqual(doc.find("li")[0].text(), payload)

    def test_null_fields_fall_back_without_manufacturing_site_or_result_state(self):
        record = {"opportunity_id": "O-SPARSE", "target_id": "T-ALT-001", "selected_format": None,
                  "modality": "antibody", "site": None, "site_id": "SITE-REGISTERED", "principal_risks": None,
                  "desired_effect": None, "result_ingestion": {"state": None}}
        doc = parse(BUILDER.render_opportunities([record]))
        fields = doc.find("dl")[0]
        values = dict(zip((n.text() for n in fields.find("dt")), (n.text() for n in fields.find("dd"))))
        self.assertEqual(values["Format"], "antibody")
        self.assertEqual(values["Site"], "SITE-REGISTERED")
        self.assertEqual(values["Desired effect"], "Not recorded")
        self.assertEqual(values["Result ingestion"], "Not recorded")
        self.assertEqual(doc.find("details"), [])
        self.assertNotIn("None", doc.text())
        self.assertNotIn("completed", doc.text().lower())


class PresentationBuilderIntegrationTests(unittest.TestCase):
    def test_provider_free_builder_packages_alternate_and_empty_views(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "atlas"
            initialized = subprocess.run([sys.executable, "-m", "surface_atlas", "init", "alternate-presentation", str(root),
                                          "--disease", "Alternate autoimmune disease", "--json"], capture_output=True, text=True)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            target_path = root / "targets.json"
            payload = json.loads(target_path.read_text())
            payload["records"] = [target()]
            target_path.write_text(json.dumps(payload))
            result = subprocess.run([sys.executable, "-m", "surface_atlas", "report", str(root), "--output-root", str(Path(directory) / "reports"),
                                     "--run-id", "alternate-snapshot", "--json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            built = json.loads(result.stdout)
            self.assertIs(built["provider_calls"], False)
            self.assertIs(built["external_urls_fetched"], False)
            output = Path(built["run_directory"])
            manifest = json.loads((output / "run-manifest.json").read_text())
            for page in ("index.html", "study.html", "explore.html", "screening.html", "target-alternate-receptor-t-alt-001.html"):
                self.assertIn(page, manifest["pages"])
                self.assertTrue((output / page).is_file())
            index = parse((output / "index.html").read_text())
            self.assertEqual(index.find("h1")[0].text(), "Alternate autoimmune disease")
            self.assertNotIn("Every entity has a disposition", index.text())
            self.assertIn("No screening results have been imported", parse((output / "screening.html").read_text()).text())
            presentation_assets = index.find("script", src="assets/presentation.js") + index.find("link", href="assets/presentation.css")
            self.assertEqual(len(presentation_assets), 2)
            for node in presentation_assets:
                self.assertTrue((output / (node.attrs.get("src") or node.attrs["href"])).is_file())
            exported = json.loads((output / "data" / "targets.json").read_text())
            self.assertIsNone(exported["records"][0]["evidence_score"]["score"])


if __name__ == "__main__":
    unittest.main()
