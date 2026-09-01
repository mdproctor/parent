"""Tests for CI doc freshness scripts."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from doc_freshness_core import parse_anchors, find_anchored_docs, detect_stale, AnchoredDoc


class TestCoreParsing(unittest.TestCase):
    """Verify the vendored core module works identically to soredium original."""

    def test_parses_full_frontmatter(self):
        content = """---
capability: notifications
audience: consumer
repo: casehub-platform
anchors:
  classes:
    - io.casehub.platform.notification.NotificationBridge
  spis:
    - io.casehub.platform.notification.spi.DeliveryChannel
---

# Notifications
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = parse_anchors(path)
            self.assertEqual(result['capability'], 'notifications')
            self.assertIn('io.casehub.platform.notification.NotificationBridge',
                          result['anchors']['classes'])
            self.assertIn('io.casehub.platform.notification.spi.DeliveryChannel',
                          result['anchors']['spis'])
        finally:
            os.unlink(path)

    def test_no_frontmatter_returns_none(self):
        content = "# Just a heading\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            self.assertIsNone(parse_anchors(path))
        finally:
            os.unlink(path)

    def test_detection_flags_matching_class(self):
        doc = AnchoredDoc(
            path='notifications.md', capability='notifications',
            audience='consumer', repo='casehub-platform',
            anchors={'classes': ['io.casehub.platform.notification.NotificationBridge']},
        )
        diff = ['platform/src/main/java/io/casehub/platform/notification/NotificationBridge.java']
        result = detect_stale(diff, [doc])
        self.assertEqual(len(result), 1)

    def test_detection_ignores_unrelated_file(self):
        doc = AnchoredDoc(
            path='notifications.md', capability='notifications',
            audience='consumer', repo='casehub-platform',
            anchors={'classes': ['io.casehub.platform.notification.NotificationBridge']},
        )
        diff = ['engine/src/main/java/io/casehub/engine/CaseEngine.java']
        result = detect_stale(diff, [doc])
        self.assertEqual(len(result), 0)


if __name__ == '__main__':
    unittest.main()
