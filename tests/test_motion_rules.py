"""Static checks of dashboard/template.html against the motion rules we follow (Emil Kowalski's design-engineering standards).

These are the review-checklist items that can be verified from the CSS text alone. Runtime behaviour (press scale, instant Escape,
no animation for keyboard-opened popovers, reduced motion) is covered by tests/ui_smoke.js.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "dashboard", "template.html"), encoding="utf-8").read()
CSS = HTML[HTML.index("<style>") + 7: HTML.index("</style>")]
COMPOSITOR_OK = {"transform", "opacity", "background-color", "color", "border-color", "clip-path"}   # no layout / paint-heavy properties


def split_top_level(value):
    """Split a CSS list on commas that are not inside parentheses (e.g. var(--d, 0ms))."""
    parts, depth, cur = [], 0, ""
    for ch in value:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


class MotionRules(unittest.TestCase):
    def test_no_transition_all(self):
        self.assertIsNone(re.search(r"transition:\s*all\b", CSS))

    def test_no_ease_in_on_ui(self):
        self.assertIsNone(re.search(r"(?<![-\w])ease-in(?![-\w])", CSS), "ease-in makes UI feel sluggish; use ease-out or a custom curve")

    def test_never_scale_from_zero(self):
        self.assertIsNone(re.search(r"scale\(\s*0\s*\)", CSS))

    def test_transitions_not_keyframes(self):
        self.assertNotIn("@keyframes", CSS, "keyframes restart from zero when interrupted; use transitions + @starting-style")

    def test_only_cheap_properties_are_transitioned(self):
        for decl in re.findall(r"transition:\s*([^;}]+)", CSS):
            for part in split_top_level(decl):
                prop = part.strip().split()[0]
                self.assertIn(prop, COMPOSITOR_OK, f"transition on '{prop}' (layout/paint property): {decl[:80]}")

    def test_ui_durations_stay_under_300ms(self):
        for decl in re.findall(r"transition(?:-duration)?:\s*([^;}]+)", CSS):
            for ms in re.findall(r"(?<![\w.-])(\d+)ms", decl):
                self.assertLessEqual(int(ms), 300, decl[:80])
        self.assertIsNone(re.search(r"transition[^;]*\b\d(?:\.\d+)?s\b(?!\w)", CSS), "use ms, and keep UI motion short")

    def test_every_hover_rule_is_gated_to_hover_capable_pointers(self):
        for line in CSS.splitlines():
            if ":hover" in line:
                self.assertIn("@media (hover: hover) and (pointer: fine)", line, line.strip()[:90])

    def test_custom_easing_curves_are_defined_and_used(self):
        self.assertIn("--ease-out: cubic-bezier(0.23, 1, 0.32, 1)", CSS)
        self.assertIn("--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)", CSS)
        self.assertGreaterEqual(CSS.count("var(--ease-out)"), 8)

    def test_press_feedback_is_subtle(self):
        scales = [float(x) for x in re.findall(r":active[^{]*\{\s*transform:\s*scale\(([\d.]+)\)", CSS)]
        self.assertTrue(scales and all(0.95 <= x <= 0.98 for x in scales), scales)

    def test_popovers_are_origin_aware_and_modal_is_centred(self):
        self.assertRegex(CSS, r"\.pop \{[^}]*transform-origin: top right")
        dlg = re.search(r"\.dlg \{[^}]*\}", CSS).group(0)
        self.assertNotIn("transform-origin", dlg, "modals keep the default centred origin")

    def test_reduced_motion_is_gentle_not_blanket_removal(self):
        block = CSS[CSS.index("@media (prefers-reduced-motion: reduce)"):]
        self.assertNotIn("transition: none", block)
        self.assertNotIn("animation: none", block)
        self.assertIn("transform: none", block)

    def test_no_live_region_wrapping_the_whole_app(self):
        self.assertNotRegex(HTML, r'id="app"[^>]*aria-live')


if __name__ == "__main__":
    unittest.main()
