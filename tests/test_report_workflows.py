from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from test_report_presentation import BUILDER, Node, SCRIPTS, WORKFLOWS, parse, target


def elements(node):
    return [child for child in node.children if isinstance(child, Node)]


class WorkflowSemanticsTests(unittest.TestCase):
    def test_overview_has_named_diagrams_and_working_section_navigation(self):
        doc = parse(WORKFLOWS.overview())
        navigation = doc.find("nav", **{"aria-label": "Overview sections"})[0]
        self.assertEqual(
            [link.attrs["href"] for link in navigation.find("a")],
            [
                "#overview-target-discovery-heading",
                "#overview-campaign-routes-heading",
                "#readout",
            ],
        )
        for link in navigation.find("a")[:2]:
            self.assertEqual(len(doc.find(id=link.attrs["href"][1:])), 1)
        diagrams = doc.find("section", **{"class": "explanatory-diagram"})
        self.assertEqual(len(diagrams), 2)
        self.assertEqual(
            [diagram.find("h3")[0].text() for diagram in diagrams],
            ["Find proteins on the cell surface", "Screen molecules or design protein binders"],
        )

    def test_screening_has_explicit_pass_and_failure_hold_review_outcomes(self):
        doc = parse(WORKFLOWS.page_diagram("screening"))
        outcomes = doc.find("div", **{"class": "wf-gate-outcomes"})[0]
        passed = outcomes.find("div", **{"class": "wf-pass"})[0].text().lower()
        failed = outcomes.find("div", **{"class": "wf-hold"})[0].text().lower()
        self.assertIn("passes", passed)
        self.assertIn("screen the library", passed)
        self.assertIn("fails", failed)
        for required in ("failed output", "review", "retest the reference before expanding"):
            self.assertIn(required, failed)
        self.assertIn("single seed cannot establish repeatability", doc.text().lower())
        self.assertIn("score repeatability does not establish pose convergence", doc.text().lower())

    def test_binder_controls_are_distinct_from_candidates_and_experiments(self):
        doc = parse(WORKFLOWS.page_diagram("binders"))
        track = doc.find("div", **{"class": "wf-control-track"})[0]
        self.assertIn("positive and negative controls", track.text())
        self.assertIn("not newly designed candidates", track.text())
        titles = [node.text().lower() for node in doc.find("h3")]
        generation = next(i for i, title in enumerate(titles) if "generate" in title)
        evaluation = next(i for i, title in enumerate(titles) if "independently" in title)
        self.assertGreater(evaluation, generation)
        self.assertIn("does not establish binding, selectivity, or efficacy", doc.text())
        overview = parse(WORKFLOWS.overview())
        experiment = overview.find("div", **{"class": "wf-future"})[0]
        self.assertIn("Next: experimental testing", experiment.text())
        self.assertIn("Measure binding, selectivity, and activity", experiment.text())

    def test_structure_diagram_preserves_experimental_predicted_and_derived_classes(self):
        doc = parse(WORKFLOWS.page_diagram("structures"))
        types = doc.find("div", **{"class": "wf-evidence-types"})[0]
        self.assertEqual([node.text() for node in types.find("strong")], ["Experimental", "Predicted", "Derived"])
        self.assertIn("gaps and uncertainty", doc.text())
        self.assertIn("support different claims", doc.text())

    def test_every_workflow_has_semantic_diagrams_hidden_decoration_and_text_steps(self):
        for key in ["overview", *WORKFLOWS.PAGE_MAPS]:
            with self.subTest(page=key):
                markup = WORKFLOWS.overview() if key == "overview" else WORKFLOWS.page_diagram(key)
                doc = parse(markup)
                figures = doc.find("figure")
                self.assertEqual(len(figures), 1)
                figure = figures[0]
                label_id = figure.attrs["aria-labelledby"]
                self.assertEqual(len(figure.find("h2", id=label_id)), 1)
                notes = figure.find("details", **{"class": "workflow-notes"})[0]
                self.assertIn("Read the workflow steps", notes.find("summary")[0].text())
                self.assertTrue(notes.find("ol"), "Workflow steps must survive without SVG or CSS")
                self.assertEqual(figure.find("script"), [])
                self.assertEqual(figure.find("h1"), [])
                semantic = [svg for svg in figure.find("svg") if "diagram-svg" in svg.attrs.get("class", "")]
                self.assertTrue(semantic)
                for panel in figure.find("section", **{"class": "explanatory-diagram"}):
                    classes = [svg.attrs.get("class", "") for svg in panel.find("svg")]
                    self.assertEqual(sum("diagram-wide" in value for value in classes), 1)
                    self.assertEqual(sum("diagram-small" in value for value in classes), 1)
                for svg in semantic:
                    self.assertEqual(svg.attrs.get("role"), "img")
                    labelled = svg.attrs.get("aria-labelledby", "").split()
                    self.assertEqual(len(labelled), 2)
                    self.assertEqual(len(figure.find("title", id=labelled[0])), 1)
                    for identifier in labelled[1:]:
                        self.assertEqual(len(figure.find("desc", id=identifier)), 1)
                decorative = [svg for svg in figure.find("svg") if svg not in semantic]
                self.assertTrue(decorative)
                self.assertTrue(all(svg.attrs.get("aria-hidden") == "true" for svg in decorative))
                ids = [node.attrs["id"] for node in figure.find() if "id" in node.attrs]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertNotIn("execution complete", figure.text().lower())

    def test_node_text_remains_data_not_markup(self):
        payload = '<script>alert("x")</script>& <img src=x>'
        node = parse(WORKFLOWS.node(WORKFLOWS.step(payload, payload, payload, payload, href="study.html", link_label=payload)))
        self.assertEqual(node.find("script"), [])
        self.assertEqual(node.find("img"), [])
        self.assertEqual(node.find("h3")[0].text(), payload)
        self.assertEqual(node.find("a")[0].text().strip(), payload + " ↗")


class WorkflowInsertionTests(unittest.TestCase):
    def test_all_page_maps_keep_records_before_diagrams_and_preserve_heading_status(self):
        for key in WORKFLOWS.PAGE_MAPS:
            with self.subTest(page=key):
                pills = '<div class="outer-status"><div class="inner-status"><span>In progress</span></div></div>'
                heading = BUILDER.page_heading("Scope", "Example", "Retain all evidence.", pills=pills)
                remainder = '<section id="actual-content"><h2>Original source evidence</h2></section>'
                body = WORKFLOWS.insert_page_diagram(heading + remainder, "targets" if key == "dossier" else key,
                                                     "Example dossier" if key == "dossier" else "Example")
                doc = parse(body)
                children = elements(doc)
                self.assertEqual([node.tag for node in children], ["div", "nav", "div", "section", "figure"])
                self.assertEqual(children[0].attrs["class"], "page-heading")
                self.assertEqual(children[0].find("figure"), [])
                self.assertEqual(children[0].find("h1")[0].text(), "Example")
                self.assertIn("In progress", children[0].text())
                navigation = children[1]
                self.assertEqual(navigation.attrs["aria-label"], "Page contents")
                self.assertEqual(navigation.find("a")[0].attrs["href"], "#workflow-" + key)
                self.assertEqual(children[2].attrs["id"], "workflow-" + key + "-records")
                self.assertEqual(children[3].attrs["id"], "actual-content")
                self.assertEqual(children[3].text(), "Original source evidence")
                figure = children[4]
                self.assertEqual(figure.attrs["id"], "workflow-" + key)
                self.assertIn("Back to results and records", figure.find("nav")[0].text())
                self.assertEqual(figure.find("nav")[0].find("a")[0].attrs["href"], "#workflow-" + key + "-records")

    def test_unknown_overview_and_missing_heading_are_unchanged(self):
        heading = BUILDER.page_heading("Example", "Untouched")
        for current, body in [("unknown-extension", heading), ("overview", heading), ("study", "<p>No generated heading</p>"),
                              ("study", '<div class="page-heading"><div>Unclosed heading')]:
            with self.subTest(page=current, body=body):
                self.assertEqual(WORKFLOWS.insert_page_diagram(body, current, "Untouched"), body)
        self.assertEqual(WORKFLOWS.page_diagram("unknown-extension"), "")


class WorkflowBundleIntegrationTests(unittest.TestCase):
    def test_alternate_atlas_packages_all_workflows_and_resolves_their_local_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "atlas"
            initialized = subprocess.run([sys.executable, "-m", "surface_atlas", "init", "alternate-workflow", str(root),
                                          "--disease", "Alternate inflammatory condition", "--json"], capture_output=True, text=True)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            record_file = root / "targets.json"
            payload = json.loads(record_file.read_text())
            payload["records"] = [target()]
            record_file.write_text(json.dumps(payload))
            result = subprocess.run([sys.executable, "-m", "surface_atlas", "report", str(root), "--output-root", str(Path(directory) / "reports"),
                                     "--run-id", "workflow-snapshot", "--json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            built = json.loads(result.stdout)
            self.assertIs(built["provider_calls"], False)
            self.assertIs(built["external_urls_fetched"], False)
            output = Path(built["run_directory"])
            manifest = json.loads((output / "run-manifest.json").read_text())
            self.assertEqual((output / "assets" / "workflows.css").read_bytes(), (SCRIPTS / "assets" / "report" / "workflows.css").read_bytes())
            pages = {"overview": "index.html", "dossier": "target-alternate-receptor-t-alt-001.html",
                     **{key: key + ".html" for key in WORKFLOWS.PAGE_MAPS if key != "dossier"}}
            for key, filename in pages.items():
                with self.subTest(page=key):
                    self.assertIn(filename, manifest["pages"])
                    doc = parse((output / filename).read_text())
                    main = doc.find("main", id="main")[0]
                    diagrams = main.find("figure", id="workflow-" + key)
                    self.assertEqual(len(diagrams), 1)
                    diagram = diagrams[0]
                    self.assertEqual(len(doc.find("link", href="assets/workflows.css")), 1)
                    self.assertFalse(any(h.find("figure") for h in main.find("div", **{"class": "page-heading"})))
                    for link in diagram.find("a"):
                        address = urlsplit(link.attrs["href"])
                        self.assertEqual(address.scheme, "")
                        self.assertEqual(address.netloc, "")
                        destination = output / (unquote(address.path) or filename)
                        self.assertTrue(destination.is_file(), str(destination))
                        if address.fragment:
                            self.assertTrue(parse(destination.read_text()).find(id=unquote(address.fragment)))
            overview = parse((output / "index.html").read_text())
            main_children = elements(overview.find("main", id="main")[0])
            metrics = next(i for i, child in enumerate(main_children) if child.attrs.get("class") == "headline-metrics")
            diagram_index = next(i for i, child in enumerate(main_children) if child.attrs.get("id") == "workflow-overview")
            self.assertEqual(diagram_index, metrics + 1)
            self.assertEqual(len(overview.find("a", href="#workflow-overview")), 1)
            self.assertEqual(overview.find("h1")[0].text(), "Alternate inflammatory condition")
            for demo_specific in ("PRIVATE-CASE-EXAMPLE", "INTERNAL-RUN-EXAMPLE"):
                self.assertNotIn(demo_specific, overview.text())


if __name__ == "__main__":
    unittest.main()
